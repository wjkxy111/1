#ifndef SMART_CAR_PID_H
#define SMART_CAR_PID_H

#include <stdint.h>

/*
 * Discrete fixed-point PID for a fixed-rate control loop.
 * Gains use x1000 scaling.  The integral term is accumulated in output
 * units, matching the active MSPM0 project so its tuning can be ported.
 */
typedef struct
{
    int32_t kp_x1000;
    int32_t ki_x1000;
    int32_t kd_x1000;
    int32_t integral;
    int32_t last_error;
    int32_t output_min;
    int32_t output_max;
    int32_t integral_min;
    int32_t integral_max;
    uint16_t initialized;
} PidController;

void Pid_Init(PidController *pid,
              int32_t kp_x1000,
              int32_t ki_x1000,
              int32_t kd_x1000,
              int32_t output_min,
              int32_t output_max);
void Pid_SetTunings(PidController *pid,
                    int32_t kp_x1000,
                    int32_t ki_x1000,
                    int32_t kd_x1000);
void Pid_SetIntegralLimits(PidController *pid,
                           int32_t integral_min,
                           int32_t integral_max);
void Pid_Reset(PidController *pid);
int32_t Pid_Update(PidController *pid,
                   int32_t setpoint,
                   int32_t feedback);

#endif
