#ifndef SMART_CAR_LINE_FOLLOW_H
#define SMART_CAR_LINE_FOLLOW_H

#include <stdint.h>

#include "line_sensor_filter.h"

#define LINE_FOLLOW_PERIOD_MS ((uint16_t) 10U)

typedef enum
{
    LINE_FOLLOW_STOPPED = 0,
    LINE_FOLLOW_TRACKING = 1,
    LINE_FOLLOW_INTERSECTION = 2,
    LINE_FOLLOW_LOST = 3,
    LINE_FOLLOW_FAILSAFE = 4
} LineFollowState;

typedef struct
{
    int16_t straight_speed;
    int16_t base_speed;
    int16_t minimum_speed;
    int16_t maximum_speed;
    int16_t lost_forward_speed;
    int16_t lost_turn_speed;
    int16_t maximum_correction;
    int32_t curve_slowdown_x100;
    int32_t kp_x100;
    int32_t kd_x100;
    int16_t output_ramp_normal;
    int16_t output_ramp_fast;
    int16_t base_ramp_step;
    int16_t correction_ramp_step;
    int16_t correction_reverse_ramp_step;
    int16_t derivative_limit_x10;
    int16_t recovery_gap_x10;
    uint16_t filter_alpha_normal_x10;
    uint16_t filter_alpha_smooth_x10;
    uint32_t lost_coast_ms;
    uint32_t lost_stop_ms;
} LineFollowConfig;

typedef struct
{
    LineFollowState state;
    uint16_t raw_mask;
    uint16_t filtered_mask;
    uint16_t active_count;
    int16_t raw_error_x10;
    int16_t error_x10;
    int16_t derivative_x10;
    int16_t last_valid_error_x10;
    int16_t p_correction;
    int16_t d_correction;
    int16_t target_correction;
    int16_t current_correction;
    int16_t current_base_speed;
    int16_t left_speed;
    int16_t right_speed;
    uint16_t motor_enable_request;
} LineFollowOutput;

typedef struct
{
    LineFollowConfig config;
    LineSensorFilter sensor_filter;
    LineFollowOutput output;
    uint32_t lost_since_ms;
    int16_t last_error_x10;
    int16_t filtered_derivative_x10;
} LineFollow;

/* Copied from the proven algorithm, but gains and speeds require car tuning. */
LineFollowConfig LineFollow_DefaultConfig(void);

/* Init and Stop never request motor enable. */
void LineFollow_Init(LineFollow *controller,
                     const LineFollowConfig *config);
void LineFollow_Start(LineFollow *controller);
void LineFollow_Stop(LineFollow *controller);
LineFollowOutput LineFollow_Step(LineFollow *controller,
                                 uint16_t raw_active_mask,
                                 uint32_t now_ms);
LineFollowOutput LineFollow_GetOutput(const LineFollow *controller);

#endif
