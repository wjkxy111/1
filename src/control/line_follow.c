#include "line_follow.h"

#define LINE_SENSOR_ALL_MASK ((uint16_t) 0x00FFU)

static int16_t LineFollow_Clamp16(int32_t value,
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

static int16_t LineFollow_Abs16(int16_t value)
{
    int32_t wide = value;
    if (wide < 0)
    {
        wide = -wide;
    }
    if (wide > 32767)
    {
        wide = 32767;
    }
    return (int16_t) wide;
}

static int16_t LineFollow_Ramp16(int16_t current,
                                 int16_t target,
                                 int16_t step)
{
    int32_t next;

    if (step < 1)
    {
        step = 1;
    }
    next = (int32_t) current + (int32_t) step;
    if ((int32_t) target > next)
    {
        return (int16_t) next;
    }
    next = (int32_t) current - (int32_t) step;
    if ((int32_t) target < next)
    {
        return (int16_t) next;
    }
    return target;
}

static int16_t LineFollow_RampCorrection(const LineFollow *controller,
                                         int16_t current,
                                         int16_t target)
{
    int16_t step = controller->config.correction_ramp_step;

    if (((current > 0) && (target < 0)) ||
        ((current < 0) && (target > 0)))
    {
        target = 0;
        step = controller->config.correction_reverse_ramp_step;
    }
    return LineFollow_Ramp16(current, target, step);
}

static void LineFollow_Output(LineFollow *controller,
                              int16_t left,
                              int16_t right,
                              int16_t slew)
{
    left = LineFollow_Clamp16((int32_t) left,
                              (int16_t) -controller->config.maximum_speed,
                              controller->config.maximum_speed);
    right = LineFollow_Clamp16((int32_t) right,
                               (int16_t) -controller->config.maximum_speed,
                               controller->config.maximum_speed);
    controller->output.left_speed = LineFollow_Ramp16(
        controller->output.left_speed, left, slew);
    controller->output.right_speed = LineFollow_Ramp16(
        controller->output.right_speed, right, slew);
}

static void LineFollow_ClearOutput(LineFollowOutput *output,
                                   LineFollowState state)
{
    output->state = state;
    output->raw_mask = 0U;
    output->filtered_mask = 0U;
    output->active_count = 0U;
    output->raw_error_x10 = 0;
    output->error_x10 = 0;
    output->derivative_x10 = 0;
    output->last_valid_error_x10 = 0;
    output->p_correction = 0;
    output->d_correction = 0;
    output->target_correction = 0;
    output->current_correction = 0;
    output->current_base_speed = 0;
    output->left_speed = 0;
    output->right_speed = 0;
    output->motor_enable_request = 0U;
}

static void LineFollow_Track(LineFollow *controller, uint32_t now_ms)
{
    int16_t raw_error;
    int16_t error_gap;
    int16_t error_delta;
    int16_t abs_error;
    int16_t base_target;
    int16_t p_correction;
    int16_t d_correction;
    int16_t target_correction;
    uint16_t alpha;

    (void) now_ms;
    raw_error = LineSensorFilter_PositionX10(
        controller->output.filtered_mask);
    controller->output.raw_error_x10 = raw_error;
    error_gap = LineFollow_Abs16((int16_t)
        (raw_error - controller->output.error_x10));
    alpha = (error_gap < controller->config.recovery_gap_x10)
        ? controller->config.filter_alpha_smooth_x10
        : controller->config.filter_alpha_normal_x10;
    if (alpha < 1U)
    {
        alpha = 1U;
    }
    if (alpha > 10U)
    {
        alpha = 10U;
    }
    controller->output.error_x10 = (int16_t)
        ((((int32_t) controller->output.error_x10 *
           (int32_t) (10U - alpha)) +
          ((int32_t) raw_error * (int32_t) alpha)) / 10);

    error_delta = (int16_t)
        (controller->output.error_x10 - controller->last_error_x10);
    controller->filtered_derivative_x10 = (int16_t)
        ((((int32_t) controller->filtered_derivative_x10 * 4) +
          (int32_t) error_delta) / 5);
    controller->filtered_derivative_x10 = LineFollow_Clamp16(
        controller->filtered_derivative_x10,
        (int16_t) -controller->config.derivative_limit_x10,
        controller->config.derivative_limit_x10);
    controller->output.derivative_x10 =
        controller->filtered_derivative_x10;
    controller->last_error_x10 = controller->output.error_x10;
    if (controller->output.error_x10 != 0)
    {
        controller->output.last_valid_error_x10 =
            controller->output.error_x10;
    }

    abs_error = LineFollow_Abs16(controller->output.error_x10);
    base_target = (int16_t)
        ((int32_t) controller->config.base_speed -
         (((int32_t) abs_error * controller->config.curve_slowdown_x100) /
          1000));
    base_target = LineFollow_Clamp16(base_target,
                                     controller->config.minimum_speed,
                                     controller->config.base_speed);
    if (base_target > controller->config.straight_speed)
    {
        base_target = controller->config.straight_speed;
    }
    controller->output.current_base_speed = LineFollow_Ramp16(
        controller->output.current_base_speed,
        base_target,
        controller->config.base_ramp_step);

    p_correction = (int16_t)
        ((controller->config.kp_x100 *
          (int32_t) controller->output.error_x10) / 1000);
    d_correction = (int16_t)
        ((controller->config.kd_x100 *
          (int32_t) controller->output.derivative_x10) / 1000);
    if ((p_correction > 0) &&
        (d_correction < (int16_t) -p_correction))
    {
        d_correction = (int16_t) -p_correction;
    }
    else if ((p_correction < 0) &&
             (d_correction > (int16_t) -p_correction))
    {
        d_correction = (int16_t) -p_correction;
    }
    target_correction = LineFollow_Clamp16(
        (int32_t) p_correction + (int32_t) d_correction,
        (int16_t) -controller->config.maximum_correction,
        controller->config.maximum_correction);
    controller->output.p_correction = p_correction;
    controller->output.d_correction = d_correction;
    controller->output.target_correction = target_correction;
    controller->output.current_correction = LineFollow_RampCorrection(
        controller,
        controller->output.current_correction,
        target_correction);
    controller->output.state = LINE_FOLLOW_TRACKING;
    LineFollow_Output(controller,
        (int16_t) (controller->output.current_base_speed +
                   controller->output.current_correction),
        (int16_t) (controller->output.current_base_speed -
                   controller->output.current_correction),
        controller->config.output_ramp_normal);
}

LineFollowConfig LineFollow_DefaultConfig(void)
{
    LineFollowConfig config;

    config.straight_speed = 37;
    config.base_speed = 30;
    config.minimum_speed = 6;
    config.maximum_speed = 50;
    config.lost_forward_speed = 8;
    config.lost_turn_speed = 14;
    config.maximum_correction = 32;
    config.curve_slowdown_x100 = 40;
    config.kp_x100 = 50;
    config.kd_x100 = 120;
    config.output_ramp_normal = 1;
    config.output_ramp_fast = 3;
    config.base_ramp_step = 1;
    config.correction_ramp_step = 2;
    config.correction_reverse_ramp_step = 1;
    config.derivative_limit_x10 = 80;
    config.recovery_gap_x10 = 80;
    config.filter_alpha_normal_x10 = 5U;
    config.filter_alpha_smooth_x10 = 2U;
    config.lost_coast_ms = 60U;
    config.lost_stop_ms = 1500U;
    return config;
}

void LineFollow_Init(LineFollow *controller,
                     const LineFollowConfig *config)
{
    if (controller == (LineFollow *) 0)
    {
        return;
    }
    controller->config = (config != (const LineFollowConfig *) 0)
        ? *config : LineFollow_DefaultConfig();
    LineSensorFilter_Init(&controller->sensor_filter);
    LineFollow_ClearOutput(&controller->output, LINE_FOLLOW_STOPPED);
    controller->lost_since_ms = 0U;
    controller->last_error_x10 = 0;
    controller->filtered_derivative_x10 = 0;
}

void LineFollow_Start(LineFollow *controller)
{
    if (controller == (LineFollow *) 0)
    {
        return;
    }
    LineSensorFilter_Reset(&controller->sensor_filter);
    LineFollow_ClearOutput(&controller->output, LINE_FOLLOW_TRACKING);
    controller->output.motor_enable_request = 1U;
    controller->lost_since_ms = 0U;
    controller->last_error_x10 = 0;
    controller->filtered_derivative_x10 = 0;
}

void LineFollow_Stop(LineFollow *controller)
{
    if (controller == (LineFollow *) 0)
    {
        return;
    }
    controller->output.left_speed = 0;
    controller->output.right_speed = 0;
    controller->output.current_base_speed = 0;
    controller->output.current_correction = 0;
    controller->output.target_correction = 0;
    controller->output.motor_enable_request = 0U;
    controller->output.state = LINE_FOLLOW_STOPPED;
}

LineFollowOutput LineFollow_Step(LineFollow *controller,
                                 uint16_t raw_active_mask,
                                 uint32_t now_ms)
{
    uint32_t lost_duration;
    int16_t direction;

    if (controller == (LineFollow *) 0)
    {
        LineFollowOutput empty;
        LineFollow_ClearOutput(&empty, LINE_FOLLOW_FAILSAFE);
        return empty;
    }
    if ((controller->output.state == LINE_FOLLOW_STOPPED) ||
        (controller->output.state == LINE_FOLLOW_FAILSAFE))
    {
        return controller->output;
    }

    controller->output.raw_mask = raw_active_mask & LINE_SENSOR_ALL_MASK;
    controller->output.filtered_mask = LineSensorFilter_Update(
        &controller->sensor_filter,
        controller->output.raw_mask);
    controller->output.active_count = LineSensorFilter_Count(
        controller->output.filtered_mask);

    if (controller->output.raw_mask == LINE_SENSOR_ALL_MASK)
    {
        controller->output.state = LINE_FOLLOW_INTERSECTION;
        controller->output.error_x10 = 0;
        controller->filtered_derivative_x10 = 0;
        controller->output.current_correction = LineFollow_Ramp16(
            controller->output.current_correction,
            0,
            controller->config.correction_ramp_step);
        controller->output.current_base_speed = LineFollow_Ramp16(
            controller->output.current_base_speed,
            controller->config.base_speed,
            controller->config.base_ramp_step);
        LineFollow_Output(controller,
            controller->output.current_base_speed,
            controller->output.current_base_speed,
            controller->config.output_ramp_normal);
        return controller->output;
    }

    if (controller->output.active_count != 0U)
    {
        if (controller->output.state == LINE_FOLLOW_LOST)
        {
            controller->filtered_derivative_x10 = 0;
            controller->last_error_x10 =
                controller->output.last_valid_error_x10;
        }
        LineFollow_Track(controller, now_ms);
        return controller->output;
    }

    if (controller->output.state != LINE_FOLLOW_LOST)
    {
        controller->lost_since_ms = now_ms;
    }
    controller->output.state = LINE_FOLLOW_LOST;
    lost_duration = now_ms - controller->lost_since_ms;
    if (lost_duration >= controller->config.lost_stop_ms)
    {
        controller->output.state = LINE_FOLLOW_FAILSAFE;
        controller->output.motor_enable_request = 0U;
        controller->output.current_base_speed = 0;
        controller->output.current_correction = 0;
        controller->output.target_correction = 0;
        controller->output.left_speed = 0;
        controller->output.right_speed = 0;
        return controller->output;
    }

    direction = (controller->output.last_valid_error_x10 < 0) ? -1 : 1;
    if (lost_duration < controller->config.lost_coast_ms)
    {
        int16_t correction = (int16_t)
            (((int32_t) direction * controller->config.lost_turn_speed) / 2);
        LineFollow_Output(controller,
            (int16_t) (controller->config.lost_forward_speed + correction),
            (int16_t) (controller->config.lost_forward_speed - correction),
            controller->config.output_ramp_fast);
    }
    else
    {
        LineFollow_Output(controller,
            (int16_t) ((int32_t) direction *
                       controller->config.lost_turn_speed),
            (int16_t) (-(int32_t) direction *
                       controller->config.lost_turn_speed),
            controller->config.output_ramp_fast);
    }
    return controller->output;
}

LineFollowOutput LineFollow_GetOutput(const LineFollow *controller)
{
    LineFollowOutput output;

    if (controller == (const LineFollow *) 0)
    {
        LineFollow_ClearOutput(&output, LINE_FOLLOW_FAILSAFE);
        return output;
    }
    return controller->output;
}
