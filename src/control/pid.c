#include "pid.h"

#include <limits.h>

static int32_t Pid_Clamp32(int64_t value, int32_t minimum, int32_t maximum)
{
    if (value > (int64_t) maximum)
    {
        return maximum;
    }
    if (value < (int64_t) minimum)
    {
        return minimum;
    }
    return (int32_t) value;
}

static int32_t Pid_ScaleGain(int32_t gain_x1000, int32_t value)
{
    int64_t product = (int64_t) gain_x1000 * (int64_t) value;
    int64_t scaled = product / (int64_t) 1000;

    if (scaled > (int64_t) INT32_MAX)
    {
        return INT32_MAX;
    }
    if (scaled < (int64_t) INT32_MIN)
    {
        return INT32_MIN;
    }
    return (int32_t) scaled;
}

void Pid_Init(PidController *pid,
              int32_t kp_x1000,
              int32_t ki_x1000,
              int32_t kd_x1000,
              int32_t output_min,
              int32_t output_max)
{
    if (pid == (PidController *) 0)
    {
        return;
    }

    if (output_min > output_max)
    {
        int32_t temporary = output_min;
        output_min = output_max;
        output_max = temporary;
    }

    pid->kp_x1000 = kp_x1000;
    pid->ki_x1000 = ki_x1000;
    pid->kd_x1000 = kd_x1000;
    pid->output_min = output_min;
    pid->output_max = output_max;
    pid->integral_min = output_min;
    pid->integral_max = output_max;
    Pid_Reset(pid);
}

void Pid_SetTunings(PidController *pid,
                    int32_t kp_x1000,
                    int32_t ki_x1000,
                    int32_t kd_x1000)
{
    if (pid == (PidController *) 0)
    {
        return;
    }
    pid->kp_x1000 = kp_x1000;
    pid->ki_x1000 = ki_x1000;
    pid->kd_x1000 = kd_x1000;
}

void Pid_SetIntegralLimits(PidController *pid,
                           int32_t integral_min,
                           int32_t integral_max)
{
    if (pid == (PidController *) 0)
    {
        return;
    }
    if (integral_min > integral_max)
    {
        int32_t temporary = integral_min;
        integral_min = integral_max;
        integral_max = temporary;
    }
    pid->integral_min = integral_min;
    pid->integral_max = integral_max;
    pid->integral = Pid_Clamp32((int64_t) pid->integral,
                               integral_min,
                               integral_max);
}

void Pid_Reset(PidController *pid)
{
    if (pid == (PidController *) 0)
    {
        return;
    }
    pid->integral = 0;
    pid->last_error = 0;
    pid->initialized = 0U;
}

int32_t Pid_Update(PidController *pid,
                   int32_t setpoint,
                   int32_t feedback)
{
    int32_t error;
    int32_t derivative;
    int32_t old_integral;
    int32_t integral_step;
    int64_t candidate_integral;
    int64_t output;

    if (pid == (PidController *) 0)
    {
        return 0;
    }

    error = Pid_Clamp32((int64_t) setpoint - (int64_t) feedback,
                        INT32_MIN,
                        INT32_MAX);
    derivative = (pid->initialized != 0U)
        ? Pid_Clamp32((int64_t) error - (int64_t) pid->last_error,
                      INT32_MIN,
                      INT32_MAX)
        : 0;
    pid->initialized = 1U;
    pid->last_error = error;

    integral_step = Pid_ScaleGain(pid->ki_x1000, error);
    old_integral = pid->integral;
    candidate_integral = (int64_t) pid->integral +
                         (int64_t) integral_step;
    pid->integral = Pid_Clamp32(candidate_integral,
                               pid->integral_min,
                               pid->integral_max);

    output = (int64_t) Pid_ScaleGain(pid->kp_x1000, error) +
             (int64_t) pid->integral +
             (int64_t) Pid_ScaleGain(pid->kd_x1000, derivative);

    /* Conditional integration prevents wind-up while output is saturated. */
    if (((output > (int64_t) pid->output_max) && (error > 0)) ||
        ((output < (int64_t) pid->output_min) && (error < 0)))
    {
        pid->integral = old_integral;
    }

    return Pid_Clamp32(output, pid->output_min, pid->output_max);
}
