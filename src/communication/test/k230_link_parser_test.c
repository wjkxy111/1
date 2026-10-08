#if defined(K230_LINK_HOST_TEST)

#include "../k230_link.h"

#include <assert.h>

typedef struct {
    K230Byte tx[256];
    uint16_t tx_length;
} TestTransport;

static uint16_t TestWrite(void *context,
                          const K230Byte *data,
                          uint16_t length)
{
    TestTransport *test = (TestTransport *)context;
    uint16_t index;

    if ((test == 0) || (data == 0) ||
        ((uint32_t)test->tx_length + length > 256U)) return 0U;
    for (index = 0U; index < length; index++) {
        test->tx[test->tx_length++] = data[index] & 0x00FFU;
    }
    return 1U;
}

static void PushText(const char *text, uint32_t now_ms)
{
    uint16_t index = 0U;
    while (text[index] != '\0') {
        /* Upper bits prove the parser masks each logical SCI octet. */
        K230Link_PushRx((K230Byte)(0xA500U | (uint16_t)text[index]), now_ms);
        index++;
    }
}

static uint16_t TxEquals(const TestTransport *test, const char *text)
{
    uint16_t index = 0U;
    if (test == 0) return 0U;
    while (text[index] != '\0') {
        if ((index >= test->tx_length) ||
            ((test->tx[index] & 0x00FFU) != (uint16_t)text[index])) return 0U;
        index++;
    }
    return (index == test->tx_length) ? 1U : 0U;
}

int main(void)
{
    TestTransport test = {{0U}, 0U};
    K230LinkTransport transport = {0, TestWrite, &test};
    K230VisionFrame vision;

    K230Link_SetTransport(&transport);
    K230Link_Init(0U);

    K230Link_RequestPrepare(3U, 10U);
    assert(TxEquals(&test, "[P3]") != 0U);
    PushText("[PREP3][R3]", 20U);
    assert(K230Link_IsReady(3U, 20U) != 0U);

    test.tx_length = 0U;
    assert(K230Link_StartTask(3U, 21U) != 0U);
    assert(TxEquals(&test, "[G3]") != 0U);
    PushText("[RUN3][+0123*][D3]", 25U);
    assert(K230Link_GetState() == K230_LINK_STATE_RUNNING);
    assert(K230Link_HasBallPosition() != 0U);
    assert(K230Link_GetBallPositionX10Mm() == 123);
    assert(K230Link_ConsumeDone(3U) != 0U);
    assert(K230Link_ConsumeDone(3U) == 0U);

    PushText("[V1,-123,450,800,3,950]", 30U);
    assert(K230Link_GetVisionFrame(&vision) != 0U);
    assert(vision.lane_error_x10_px == -123);
    assert(vision.curvature_x10000 == 450);
    assert(vision.obstacle_distance_mm == 800U);
    assert(vision.sign == K230_VISION_SIGN_STOP);
    assert(vision.confidence_x1000 == 950U);
    assert(K230Link_IsVisionFresh(100U, 100U) != 0U);
    assert(K230Link_IsVisionFresh(131U, 100U) == 0U);

    PushText("[V1,1,2,3,4,1001]", 40U);
    assert(K230Link_GetRxErrorCount() == 1U);
    assert(K230Link_GetRxFrameCount() == 7U);

    test.tx_length = 0U;
    assert(K230Link_SendFeedforwardSample(7U, -12, 34, -56) != 0U);
    assert(TxEquals(&test, "[FA,7,-12,34,-56]") != 0U);

    test.tx_length = 0U;
    K230Link_Stop(50U);
    assert(TxEquals(&test, "[S]") != 0U);
    PushText("[IDLE]", 51U);
    assert(K230Link_GetState() == K230_LINK_STATE_IDLE);
    return 0;
}

#endif /* K230_LINK_HOST_TEST */
