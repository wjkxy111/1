//#############################################################################
//
// FILE:   empty_driverlib_main.c
//
//! \addtogroup driver_example_list
//! <h1>Empty Project Example</h1> 
//!
//! This example is an empty project setup for Driverlib development.
//!
//
//#############################################################################
//
//
// 
// C2000Ware v26.01.00.00
//
// Copyright (C) 2024 Texas Instruments Incorporated - http://www.ti.com
//
// Redistribution and use in source and binary forms, with or without 
// modification, are permitted provided that the following conditions 
// are met:
// 
//   Redistributions of source code must retain the above copyright 
//   notice, this list of conditions and the following disclaimer.
// 
//   Redistributions in binary form must reproduce the above copyright
//   notice, this list of conditions and the following disclaimer in the 
//   documentation and/or other materials provided with the   
//   distribution.
// 
//   Neither the name of Texas Instruments Incorporated nor the names of
//   its contributors may be used to endorse or promote products derived
//   from this software without specific prior written permission.
// 
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 
// "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT 
// LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
// A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT 
// OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, 
// SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT 
// LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
// DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
// THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT 
// (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE 
// OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
// $
//#############################################################################

//
// Included Files
//
#include "driverlib.h"
#include "device.h"
#include "board.h"

#include "src/communication/k230_link.h"
#include "src/control/encoder_snapshot.h"
#include "src/control/line_follow.h"
#include "src/control/motor_control.h"
#include "src/platform/hal.h"

#define APP_VISION_FRESH_MS          (200UL)
#define APP_VISION_MIN_CONFIDENCE    (700U)
#define APP_OBSTACLE_STOP_MM         (300U)
#define APP_SPEED_LIMIT_PERCENT      (50)
#define APP_VISION_CORRECTION_LIMIT  (12)

typedef enum
{
    APP_STATE_SAFE = 0,
    APP_STATE_RUNNING,
    APP_STATE_FAULT
} AppState;

static EncoderSnapshotBuilder g_encoderBuilder;
static LineFollow g_lineFollower;
static MotorControl g_motorControl;
static AppState g_appState = APP_STATE_SAFE;
static uint32_t g_nowMs = 0UL;

static int16_t App_clamp16(int32_t value, int16_t minimum, int16_t maximum)
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

static uint16_t App_k230Read(void *context, K230Byte *data)
{
    uint16_t byteValue;

    (void) context;
    if ((data == (K230Byte *) 0) || !HAL_k230TryReadByte(&byteValue))
    {
        return 0U;
    }
    *data = (K230Byte) (byteValue & 0x00FFU);
    return 1U;
}

static uint16_t App_k230Write(void *context,
                              const K230Byte *data,
                              uint16_t length)
{
    uint16_t index;
    uint32_t spin;

    (void) context;
    if ((data == (const K230Byte *) 0) || (length == 0U))
    {
        return 0U;
    }
    for (index = 0U; index < length; index++)
    {
        for (spin = 0UL; spin < 200000UL; spin++)
        {
            if (HAL_k230TryWriteByte((uint16_t) data[index] & 0x00FFU))
            {
                break;
            }
        }
        if (spin == 200000UL)
        {
            return 0U;
        }
    }
    return 1U;
}

static void App_stop(AppState state)
{
    LineFollow_Stop(&g_lineFollower);
    MotorControl_Disarm(&g_motorControl);
    HAL_motorEmergencyStop();
    g_appState = state;
}

static void App_start(void)
{
    uint16_t sensors = HAL_trackReadActiveLow();

    /* A deliberate command and a visible track are both required. */
    if ((sensors == 0U) || (sensors == 0x00FFU))
    {
        App_stop(APP_STATE_SAFE);
        return;
    }
    HAL_encoderReset();
    EncoderSnapshot_Reset(&g_encoderBuilder, 0L, 0L);
    MotorControl_ClearFault(&g_motorControl);
    MotorControl_Arm(&g_motorControl);
    LineFollow_Start(&g_lineFollower);
    HAL_motorEnable(true);
    g_appState = APP_STATE_RUNNING;
}

static void App_processDebugCommand(void)
{
    uint16_t command;

    while (HAL_debugTryReadByte(&command))
    {
        command &= 0x00FFU;
        if ((command == (uint16_t) 'g') || (command == (uint16_t) 'G'))
        {
            App_start();
        }
        else if ((command == (uint16_t) 'x') ||
                 (command == (uint16_t) 'X') ||
                 (command == 0x001BU))
        {
            App_stop(APP_STATE_SAFE);
        }
        else if ((command == (uint16_t) 'r') || (command == (uint16_t) 'R'))
        {
            App_stop(APP_STATE_SAFE);
            MotorControl_ClearFault(&g_motorControl);
        }
    }
}

static uint16_t App_applyVision(LineFollowOutput *lineOutput)
{
    K230VisionFrame vision;
    int16_t correction;

    if ((lineOutput == (LineFollowOutput *) 0) ||
        !K230Link_IsVisionFresh(g_nowMs, APP_VISION_FRESH_MS) ||
        !K230Link_GetVisionFrame(&vision) ||
        (vision.confidence_x1000 < APP_VISION_MIN_CONFIDENCE))
    {
        return 1U;
    }

    if ((vision.sign == K230_VISION_SIGN_STOP) ||
        ((vision.obstacle_distance_mm != 0U) &&
         (vision.obstacle_distance_mm <= APP_OBSTACLE_STOP_MM)))
    {
        return 0U;
    }

    if (vision.sign == K230_VISION_SIGN_SPEED_LIMIT)
    {
        lineOutput->left_speed = (int16_t)
            (((int32_t) lineOutput->left_speed * APP_SPEED_LIMIT_PERCENT) / 100);
        lineOutput->right_speed = (int16_t)
            (((int32_t) lineOutput->right_speed * APP_SPEED_LIMIT_PERCENT) / 100);
    }

    correction = App_clamp16((int32_t) vision.lane_error_x10_px / 50L,
                              (int16_t) -APP_VISION_CORRECTION_LIMIT,
                              (int16_t) APP_VISION_CORRECTION_LIMIT);
    lineOutput->left_speed = App_clamp16(
        (int32_t) lineOutput->left_speed + correction, -100, 100);
    lineOutput->right_speed = App_clamp16(
        (int32_t) lineOutput->right_speed - correction, -100, 100);
    return 1U;
}

static void App_controlStep(void)
{
    EncoderSnapshot encoder;
    LineFollowOutput lineOutput;
    MotorControlOutput motorOutput;

    encoder = EncoderSnapshot_Update(
        &g_encoderBuilder,
        (int32_t) HAL_encoderGetLeft(),
        (int32_t) HAL_encoderGetRight());

    if (g_appState != APP_STATE_RUNNING)
    {
        HAL_motorEmergencyStop();
        return;
    }

    lineOutput = LineFollow_Step(&g_lineFollower,
                                 HAL_trackReadActiveLow(),
                                 g_nowMs);
    if ((lineOutput.motor_enable_request == 0U) ||
        (lineOutput.state == LINE_FOLLOW_FAILSAFE) ||
        !App_applyVision(&lineOutput))
    {
        App_stop(APP_STATE_FAULT);
        return;
    }

    MotorControl_SetTarget(&g_motorControl,
                           lineOutput.left_speed,
                           lineOutput.right_speed);
    motorOutput = MotorControl_Step(&g_motorControl, &encoder);
    if (motorOutput.state != MOTOR_CONTROL_ARMED)
    {
        App_stop(APP_STATE_FAULT);
        return;
    }
    HAL_motorSetPermille((int16_t) ((int32_t) motorOutput.left_duty * 10L),
                           (int16_t) ((int32_t) motorOutput.right_duty * 10L));
}

//
// Main
//
void main(void)
{

    K230LinkTransport k230Transport;

    //
    // Initialize device clock and peripherals
    //
    Device_init();

    //
    // Disable pin locks and enable internal pull-ups.
    //
    Device_initGPIO();

    //
    // Initialize PIE and clear PIE registers. Disables CPU interrupts.
    //
    Interrupt_initModule();

    //
    // Initialize the PIE vector table with pointers to the shell Interrupt
    // Service Routines (ISR).
    //
    Interrupt_initVectorTable();

    //
    // PinMux and Peripheral Initialization
    //
    Board_init();

    HAL_init();
    EncoderSnapshot_Init(&g_encoderBuilder);
    EncoderSnapshot_Reset(&g_encoderBuilder,
                          (int32_t) HAL_encoderGetLeft(),
                          (int32_t) HAL_encoderGetRight());
    LineFollow_Init(&g_lineFollower, (const LineFollowConfig *) 0);
    MotorControl_Init(&g_motorControl, (const MotorControlConfig *) 0);

    k230Transport.read_byte = App_k230Read;
    k230Transport.write = App_k230Write;
    k230Transport.context = (void *) 0;
    K230Link_SetTransport(&k230Transport);
    K230Link_Init(g_nowMs);

    /* Fail-safe boot policy: motor power stays disabled until debug UART
     * receives an explicit 'g' and at least one valid line sensor is active. */
    App_stop(APP_STATE_SAFE);

    //
    // Enable Global Interrupt (INTM) and real time interrupt (DBGM)
    //
    EINT;
    ERTM;

    while(1)
    {
        App_processDebugCommand();
        if (HAL_take1msTick())
        {
            g_nowMs++;
            K230Link_Update(g_nowMs, 1U, 0U);
        }
        if (HAL_take10msTick())
        {
            App_controlStep();
        }
    }
}

//
// End of File
//
