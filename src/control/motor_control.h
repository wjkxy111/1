#ifndef SMART_CAR_MOTOR_CONTROL_H
#define SMART_CAR_MOTOR_CONTROL_H

#include <stdint.h>

#include "encoder_snapshot.h"
#include "pid.h"

#define MOTOR_CONTROL_PERIOD_MS ((uint16_t) 10U)

typedef enum
{
    MOTOR_CONTROL_DISARMED = 0,
    MOTOR_CONTROL_ARMED = 1,
    MOTOR_CONTROL_FAULT = 2
} MotorControlState;

typedef struct
{
    int32_t speed_100_percent_cps;
    int32_t kp_x1000;
    int32_t ki_x1000;
    int32_t kd_x1000;
    int32_t filtered_cps_divisor;
    int16_t command_limit;
    int16_t duty_limit;
} MotorControlConfig;

typedef struct
{
    int16_t left_target;
    int16_t right_target;
    int16_t left_feedback;
    int16_t right_feedback;
    int16_t left_duty;
    int16_t right_duty;
    int32_t left_filtered_cps;
    int32_t right_filtered_cps;
    MotorControlState state;
    uint32_t update_count;
} MotorControlOutput;

typedef struct
{
    MotorControlConfig config;
    PidController speed_pid[2];
    int16_t target[2];
    int16_t previous_target[2];
    int32_t filtered_cps[2];
    MotorControlOutput output;
} MotorControl;

/* Conservative starting point copied from the active G3507 project.
 * It MUST be re-identified and retuned on the F28P650 vehicle. */
MotorControlConfig MotorControl_DefaultConfig(void);

/* Init is fail-safe: state is DISARMED and both duties are zero. */
void MotorControl_Init(MotorControl *control,
                       const MotorControlConfig *config);
void MotorControl_Arm(MotorControl *control);
void MotorControl_Disarm(MotorControl *control);
void MotorControl_SetFault(MotorControl *control);
void MotorControl_ClearFault(MotorControl *control);
void MotorControl_SetTarget(MotorControl *control,
                            int16_t left_speed,
                            int16_t right_speed);
MotorControlOutput MotorControl_Step(MotorControl *control,
                                     const EncoderSnapshot *snapshot);
MotorControlOutput MotorControl_GetOutput(const MotorControl *control);

#endif
