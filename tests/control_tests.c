#if defined(CONTROL_HOST_TEST)

#include <assert.h>
#include <stdio.h>

#include "encoder_snapshot.h"
#include "line_follow.h"
#include "line_sensor_filter.h"
#include "motor_control.h"
#include "pid.h"

static void test_pid(void)
{
    PidController pid;

    Pid_Init(&pid, 1000, 0, 0, -100, 100);
    assert(Pid_Update(&pid, 20, 0) == 20);
    assert(Pid_Update(&pid, 200, 0) == 100);
}

static void test_encoder_snapshot(void)
{
    EncoderSnapshotBuilder builder;
    EncoderSnapshot snapshot;

    EncoderSnapshot_Init(&builder);
    snapshot = EncoderSnapshot_Update(&builder, 100, -20);
    assert(snapshot.valid == 0U);
    snapshot = EncoderSnapshot_Update(&builder, 104, -18);
    assert(snapshot.valid != 0U);
    assert(snapshot.left_delta_count == 4);
    assert(snapshot.right_delta_count == 2);
    assert(snapshot.left_counts_per_second == 400);
    assert(snapshot.right_counts_per_second == 200);
}

static void test_motor_is_safe_until_armed(void)
{
    MotorControl motor;
    EncoderSnapshot snapshot = {0};
    MotorControlOutput output;

    MotorControl_Init(&motor, (const MotorControlConfig *) 0);
    MotorControl_SetTarget(&motor, 30, 30);
    snapshot.valid = 1U;
    output = MotorControl_Step(&motor, &snapshot);
    assert(output.state == MOTOR_CONTROL_DISARMED);
    assert(output.left_duty == 0);
    assert(output.right_duty == 0);

    MotorControl_Arm(&motor);
    MotorControl_SetTarget(&motor, 30, 30);
    output = MotorControl_Step(&motor, &snapshot);
    assert(output.state == MOTOR_CONTROL_ARMED);
    assert(output.left_duty > 0);
    assert(output.right_duty > 0);

    MotorControl_Disarm(&motor);
    output = MotorControl_GetOutput(&motor);
    assert(output.left_duty == 0);
    assert(output.right_duty == 0);
}

static void test_line_filter_and_state_machine(void)
{
    LineSensorFilter filter;
    LineFollow follow;
    LineFollowOutput output;

    LineSensorFilter_Init(&filter);
    assert(LineSensorFilter_Update(&filter, 0x18U) == 0x18U);
    assert(LineSensorFilter_PositionX10(0x18U) == 0);
    assert(LineSensorFilter_PositionX10(0x01U) > 0);
    assert(LineSensorFilter_PositionX10(0x80U) < 0);

    LineFollow_Init(&follow, (const LineFollowConfig *) 0);
    output = LineFollow_GetOutput(&follow);
    assert(output.state == LINE_FOLLOW_STOPPED);
    assert(output.motor_enable_request == 0U);

    LineFollow_Start(&follow);
    output = LineFollow_Step(&follow, 0x18U, 10U);
    assert(output.state == LINE_FOLLOW_TRACKING);
    assert(output.motor_enable_request != 0U);
    assert(output.left_speed == output.right_speed);

    output = LineFollow_Step(&follow, 0xFFU, 20U);
    assert(output.state == LINE_FOLLOW_INTERSECTION);
    assert(output.left_speed == output.right_speed);

    (void) LineFollow_Step(&follow, 0x00U, 30U);
    (void) LineFollow_Step(&follow, 0x00U, 40U);
    (void) LineFollow_Step(&follow, 0x00U, 50U);
    output = LineFollow_Step(&follow, 0x00U, 1600U);
    assert(output.state == LINE_FOLLOW_FAILSAFE);
    assert(output.motor_enable_request == 0U);
    assert(output.left_speed == 0);
    assert(output.right_speed == 0);
}

int main(void)
{
    test_pid();
    test_encoder_snapshot();
    test_motor_is_safe_until_armed();
    test_line_filter_and_state_machine();
    puts("control_tests: PASS");
    return 0;
}

#endif
