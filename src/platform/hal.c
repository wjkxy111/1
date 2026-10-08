#include "hal.h"

#include <limits.h>

#include "board.h"
#include "driverlib.h"

#if (CHAR_BIT != 16)
#error "This HAL requires the C28x ABI with 16-bit char."
#endif

#define HAL_PWM_PERIOD_COUNTS        (10000UL)
#define HAL_COMMAND_MAX_PERMILLE     (1000)
#define HAL_BYTE_MASK                (0x00FFU)
#define HAL_TRACK_MASK               ((1U << HAL_TRACK_SENSOR_COUNT) - 1U)

static bool s_motorEnabled = false;
static int16_t s_leftCommand = 0;
static int16_t s_rightCommand = 0;

static int16_t HAL_clampCommand(int16_t command)
{
    if(command > HAL_COMMAND_MAX_PERMILLE)
    {
        return HAL_COMMAND_MAX_PERMILLE;
    }
    if(command < -HAL_COMMAND_MAX_PERMILLE)
    {
        return -HAL_COMMAND_MAX_PERMILLE;
    }
    return command;
}

static uint16_t HAL_absCommand(int16_t command)
{
    int32_t extended = command;
    return (uint16_t)((extended < 0) ? -extended : extended);
}

static uint16_t HAL_commandToCompare(int16_t command)
{
    uint32_t magnitude = HAL_absCommand(command);
    uint32_t compare = (magnitude * HAL_PWM_PERIOD_COUNTS) /
                       (uint32_t)HAL_COMMAND_MAX_PERMILLE;

    // In edge-aligned mode CMPA == TBPRD + 1 produces a full-period high.
    return (uint16_t)compare;
}

static void HAL_applyMotorOutputs(void)
{
    uint16_t leftCompare = 0U;
    uint16_t rightCompare = 0U;

    GPIO_writePin(MOTOR_LEFT_DIR, (s_leftCommand < 0) ? 1U : 0U);
    GPIO_writePin(MOTOR_RIGHT_DIR, (s_rightCommand < 0) ? 1U : 0U);

    // Set CMPA before releasing the continuous software force. This prevents
    // one stale PWM pulse during the DISABLED -> ENABLED transition.
    if(s_motorEnabled)
    {
        leftCompare = HAL_commandToCompare(s_leftCommand);
        rightCompare = HAL_commandToCompare(s_rightCommand);
    }

    EPWM_setCounterCompareValue(MOTOR_LEFT_PWM_BASE,
                                EPWM_COUNTER_COMPARE_A, leftCompare);
    EPWM_setCounterCompareValue(MOTOR_RIGHT_PWM_BASE,
                                EPWM_COUNTER_COMPARE_A, rightCompare);

    EPWM_setActionQualifierContSWForceAction(
        MOTOR_LEFT_PWM_BASE, EPWM_AQ_OUTPUT_A,
        s_motorEnabled ? EPWM_AQ_SW_DISABLED : EPWM_AQ_SW_OUTPUT_LOW);
    EPWM_setActionQualifierContSWForceAction(
        MOTOR_RIGHT_PWM_BASE, EPWM_AQ_OUTPUT_A,
        s_motorEnabled ? EPWM_AQ_SW_DISABLED : EPWM_AQ_SW_OUTPUT_LOW);
}

static uint32_t HAL_motorEnableLevel(bool enabled)
{
#if (HAL_MOTOR_ENABLE_ACTIVE_HIGH != 0U)
    return enabled ? 1U : 0U;
#else
    return enabled ? 0U : 1U;
#endif
}

static bool HAL_sciTryRead(uint32_t base, uint16_t *byteValue)
{
    if((byteValue == 0) || !SCI_isDataAvailableNonFIFO(base))
    {
        return false;
    }

    *byteValue = SCI_readCharNonBlocking(base) & HAL_BYTE_MASK;
    return true;
}

static bool HAL_sciTryWrite(uint32_t base, uint16_t byteValue)
{
    if(!SCI_isSpaceAvailableNonFIFO(base))
    {
        return false;
    }

    SCI_writeCharNonBlocking(base, byteValue & HAL_BYTE_MASK);
    return true;
}

void HAL_init(void)
{
    s_leftCommand = 0;
    s_rightCommand = 0;
    s_motorEnabled = false;

    // Enforce the active-high default even if Board_init() is called elsewhere.
    GPIO_writePin(MOTOR_LEFT_EN, HAL_motorEnableLevel(false));
    GPIO_writePin(MOTOR_RIGHT_EN, HAL_motorEnableLevel(false));
    HAL_applyMotorOutputs();

    CPUTimer_clearOverflowFlag(CONTROL_TICK_1MS_BASE);
    CPUTimer_clearOverflowFlag(SERVICE_TICK_10MS_BASE);
}

void HAL_motorEmergencyStop(void)
{
    s_motorEnabled = false;
    s_leftCommand = 0;
    s_rightCommand = 0;

    // Disable the external bridge first, then update PWM/command state.
    GPIO_writePin(MOTOR_LEFT_EN, HAL_motorEnableLevel(false));
    GPIO_writePin(MOTOR_RIGHT_EN, HAL_motorEnableLevel(false));
    HAL_applyMotorOutputs();
}

void HAL_motorEnable(bool enable)
{
    if(enable)
    {
        s_motorEnabled = true;
        HAL_applyMotorOutputs();
        GPIO_writePin(MOTOR_LEFT_EN, HAL_motorEnableLevel(true));
        GPIO_writePin(MOTOR_RIGHT_EN, HAL_motorEnableLevel(true));
    }
    else
    {
        HAL_motorEmergencyStop();
    }
}

bool HAL_motorIsEnabled(void)
{
    return s_motorEnabled;
}

void HAL_motorSetPermille(int16_t left, int16_t right)
{
    s_leftCommand = HAL_clampCommand(left);
    s_rightCommand = HAL_clampCommand(right);
    HAL_applyMotorOutputs();
}

uint32_t HAL_encoderGetLeft(void)
{
    return EQEP_getPosition(ENCODER_LEFT_BASE);
}

uint32_t HAL_encoderGetRight(void)
{
    return EQEP_getPosition(ENCODER_RIGHT_BASE);
}

void HAL_encoderReset(void)
{
    bool interruptsWereDisabled = Interrupt_disableGlobal();

    EQEP_setPosition(ENCODER_LEFT_BASE, 0UL);
    EQEP_setPosition(ENCODER_RIGHT_BASE, 0UL);

    if(!interruptsWereDisabled)
    {
        (void)Interrupt_enableGlobal();
    }
}

uint16_t HAL_trackReadRaw(void)
{
    static const uint16_t trackPins[HAL_TRACK_SENSOR_COUNT] =
    {
        TRACK_0, TRACK_1, TRACK_2, TRACK_3,
        TRACK_4, TRACK_5, TRACK_6, TRACK_7
    };
    uint16_t sample = 0U;
    uint16_t index;

    for(index = 0U; index < HAL_TRACK_SENSOR_COUNT; ++index)
    {
        if(GPIO_readPin(trackPins[index]) != 0U)
        {
            sample |= (uint16_t)(1U << index);
        }
    }

    return sample;
}

uint16_t HAL_trackReadActiveLow(void)
{
    return (uint16_t)(~HAL_trackReadRaw()) & HAL_TRACK_MASK;
}

bool HAL_k230TryReadByte(uint16_t *byteValue)
{
    return HAL_sciTryRead(K230_SCI_BASE, byteValue);
}

bool HAL_k230TryWriteByte(uint16_t byteValue)
{
    return HAL_sciTryWrite(K230_SCI_BASE, byteValue);
}

bool HAL_debugTryReadByte(uint16_t *byteValue)
{
    return HAL_sciTryRead(DEBUG_SCI_BASE, byteValue);
}

bool HAL_debugTryWriteByte(uint16_t byteValue)
{
    return HAL_sciTryWrite(DEBUG_SCI_BASE, byteValue);
}

bool HAL_take1msTick(void)
{
    if(!CPUTimer_getTimerOverflowStatus(CONTROL_TICK_1MS_BASE))
    {
        return false;
    }

    CPUTimer_clearOverflowFlag(CONTROL_TICK_1MS_BASE);
    return true;
}

bool HAL_take10msTick(void)
{
    if(!CPUTimer_getTimerOverflowStatus(SERVICE_TICK_10MS_BASE))
    {
        return false;
    }

    CPUTimer_clearOverflowFlag(SERVICE_TICK_10MS_BASE);
    return true;
}
