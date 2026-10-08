#include "motor_control.h"

#define MOTOR_LEFT_INDEX  (0U)
#define MOTOR_RIGHT_INDEX (1U)

static int16_t MotorControl_Clamp16(int32_t value,
                                    int16_t minimum,
                                    int16_t maximum)
{
    if (value > (int32_t) maximum)
    {
        return maximum;
    }
    if (value < (int32_t) minimum)
    {
        return minimum;
    }
    return (int16_t) value;
}

static int16_t MotorControl_CpsToCommand(const MotorControl *control,
                                         int32_t counts_per_second)
{
    int64_t scaled;

    if ((control == (const MotorControl *) 0) ||
        (control->config.speed_100_percent_cps <= 0))
    {
        return 0;
    }
    scaled = ((int64_t) counts_per_second * (int64_t) 100) /
             (int64_t) control->config.speed_100_percent_cps;
    if (scaled > (int64_t) control->config.command_limit)
    {
        return control->config.command_limit;
    }
    if (scaled < -(int64_t) control->config.command_limit)
    {
        return (int16_t) -control->config.command_limit;
    }
    return (int16_t) scaled;
}

static void MotorControl_ResetLoops(MotorControl *control)
{
    uint16_t side;

    for (side = 0U; side < 2U; side++)
    {
        Pid_Reset(&control->speed_pid[side]);
        control->previous_target[side] = 0;
    }
}

static void MotorControl_ZeroOutput(MotorControl *control)
{
    control->output.left_target = 0;
    control->output.right_target = 0;
    control->output.left_duty = 0;
    control->output.right_duty = 0;
}

MotorControlConfig MotorControl_DefaultConfig(void)
{
    MotorControlConfig config;

    config.speed_100_percent_cps = 4000;
    config.kp_x1000 = 2800;
    config.ki_x1000 = 10;
    config.kd_x1000 = 0;
    config.filtered_cps_divisor = 5;
    config.command_limit = 100;
    config.duty_limit = 100;
    return config;
}

void MotorControl_Init(MotorControl *control,
                       const MotorControlConfig *config)
{
    MotorControlConfig selected;
    uint16_t side;

    if (control == (MotorControl *) 0)
    {
        return;
    }
    selected = (config != (const MotorControlConfig *) 0)
        ? *config : MotorControl_DefaultConfig();
    if (selected.speed_100_percent_cps <= 0)
    {
        selected.speed_100_percent_cps = 1;
    }
    if (selected.filtered_cps_divisor < 1)
    {
        selected.filtered_cps_divisor = 1;
    }
    if ((selected.command_limit < 1) || (selected.command_limit > 100))
    {
        selected.command_limit = 100;
    }
    if ((selected.duty_limit < 1) || (selected.duty_limit > 100))
    {
        selected.duty_limit = 100;
    }

    control->config = selected;
    for (side = 0U; side < 2U; side++)
    {
        Pid_Init(&control->speed_pid[side],
                 selected.kp_x1000,
                 selected.ki_x1000,
                 selected.kd_x1000,
                 -(int32_t) selected.duty_limit,
                 (int32_t) selected.duty_limit);
        Pid_SetIntegralLimits(&control->speed_pid[side],
                              -(int32_t) selected.duty_limit,
                              (int32_t) selected.duty_limit);
        control->target[side] = 0;
        control->previous_target[side] = 0;
        control->filtered_cps[side] = 0;
    }
    control->output = (MotorControlOutput) {0};
    control->output.state = MOTOR_CONTROL_DISARMED;
}

void MotorControl_Arm(MotorControl *control)
{
    if ((control == (MotorControl *) 0) ||
        (control->output.state == MOTOR_CONTROL_FAULT))
    {
        return;
    }
    control->target[MOTOR_LEFT_INDEX] = 0;
    control->target[MOTOR_RIGHT_INDEX] = 0;
    MotorControl_ResetLoops(control);
    MotorControl_ZeroOutput(control);
    control->output.state = MOTOR_CONTROL_ARMED;
}

void MotorControl_Disarm(MotorControl *control)
{
    if (control == (MotorControl *) 0)
    {
        return;
    }
    control->target[MOTOR_LEFT_INDEX] = 0;
    control->target[MOTOR_RIGHT_INDEX] = 0;
    MotorControl_ResetLoops(control);
    MotorControl_ZeroOutput(control);
    control->output.state = MOTOR_CONTROL_DISARMED;
}

void MotorControl_SetFault(MotorControl *control)
{
    if (control == (MotorControl *) 0)
    {
        return;
    }
    MotorControl_Disarm(control);
    control->output.state = MOTOR_CONTROL_FAULT;
}

void MotorControl_ClearFault(MotorControl *control)
{
    if (control == (MotorControl *) 0)
    {
        return;
    }
    MotorControl_Disarm(control);
}

void MotorControl_SetTarget(MotorControl *control,
                            int16_t left_speed,
                            int16_t right_speed)
{
    if ((control == (MotorControl *) 0) ||
        (control->output.state != MOTOR_CONTROL_ARMED))
    {
        return;
    }
    control->target[MOTOR_LEFT_INDEX] = MotorControl_Clamp16(
        (int32_t) left_speed,
        (int16_t) -control->config.command_limit,
        control->config.command_limit);
    control->target[MOTOR_RIGHT_INDEX] = MotorControl_Clamp16(
        (int32_t) right_speed,
        (int16_t) -control->config.command_limit,
        control->config.command_limit);
}

MotorControlOutput MotorControl_Step(MotorControl *control,
                                     const EncoderSnapshot *snapshot)
{
    int32_t measured_cps[2];
    uint16_t side;

    if (control == (MotorControl *) 0)
    {
        MotorControlOutput empty = {0};
        empty.state = MOTOR_CONTROL_FAULT;
        return empty;
    }
    if ((snapshot == (const EncoderSnapshot *) 0) ||
        (snapshot->valid == 0U))
    {
        MotorControl_SetFault(control);
        return control->output;
    }
    if (control->output.state != MOTOR_CONTROL_ARMED)
    {
        MotorControl_ZeroOutput(control);
        return control->output;
    }

    measured_cps[MOTOR_LEFT_INDEX] = snapshot->left_counts_per_second;
    measured_cps[MOTOR_RIGHT_INDEX] = snapshot->right_counts_per_second;

    for (side = 0U; side < 2U; side++)
    {
        int32_t duty;
        int16_t feedback;
        int16_t target = control->target[side];

        control->filtered_cps[side] +=
            (measured_cps[side] - control->filtered_cps[side]) /
            control->config.filtered_cps_divisor;
        feedback = MotorControl_CpsToCommand(control,
                                             control->filtered_cps[side]);

        if (target == 0)
        {
            Pid_Reset(&control->speed_pid[side]);
            duty = 0;
        }
        else
        {
            if (((target > 0) && (control->previous_target[side] <= 0)) ||
                ((target < 0) && (control->previous_target[side] >= 0)))
            {
                Pid_Reset(&control->speed_pid[side]);
            }
            duty = Pid_Update(&control->speed_pid[side], target, feedback);

            /* Overshoot releases drive; it never reverses the H bridge. */
            if (((target > 0) && (duty < 0)) ||
                ((target < 0) && (duty > 0)))
            {
                duty = 0;
            }
        }
        control->previous_target[side] = target;

        if (side == MOTOR_LEFT_INDEX)
        {
            control->output.left_target = target;
            control->output.left_feedback = feedback;
            control->output.left_duty = (int16_t) duty;
        }
        else
        {
            control->output.right_target = target;
            control->output.right_feedback = feedback;
            control->output.right_duty = (int16_t) duty;
        }
    }

    control->output.left_filtered_cps =
        control->filtered_cps[MOTOR_LEFT_INDEX];
    control->output.right_filtered_cps =
        control->filtered_cps[MOTOR_RIGHT_INDEX];
    control->output.update_count++;
    return control->output;
}

MotorControlOutput MotorControl_GetOutput(const MotorControl *control)
{
    MotorControlOutput output = {0};

    if (control == (const MotorControl *) 0)
    {
        output.state = MOTOR_CONTROL_FAULT;
        return output;
    }
    return control->output;
}
