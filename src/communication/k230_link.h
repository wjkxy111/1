#ifndef K230_LINK_H
#define K230_LINK_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * C28x note: CHAR_BIT is 16 and uint8_t is a 16-bit C object. A K230Byte
 * stores one logical UART octet in bits 7..0. Transport callbacks and
 * K230Link_PushRx() clear the upper bits at the SCI boundary.
 */
typedef uint16_t K230Byte;

typedef uint16_t (*K230LinkReadByteFn)(void *context, K230Byte *data);
typedef uint16_t (*K230LinkWriteFn)(void *context,
                                    const K230Byte *data,
                                    uint16_t length);

typedef struct {
    K230LinkReadByteFn read_byte;
    K230LinkWriteFn write;
    void *context;
} K230LinkTransport;

typedef enum {
    K230_LINK_STATE_OFFLINE = 0,
    K230_LINK_STATE_IDLE,
    K230_LINK_STATE_PREPARING,
    K230_LINK_STATE_CENTERING_TASK6,
    K230_LINK_STATE_SETTING_TASK6,
    K230_LINK_STATE_LOCKING_TASK6,
    K230_LINK_STATE_READY,
    K230_LINK_STATE_RUNNING,
    K230_LINK_STATE_RETURNING,
    K230_LINK_STATE_ERROR
} K230LinkState;

typedef enum {
    K230_VISION_SIGN_NONE = 0,
    K230_VISION_SIGN_LEFT,
    K230_VISION_SIGN_RIGHT,
    K230_VISION_SIGN_STOP,
    K230_VISION_SIGN_SPEED_LIMIT,
    K230_VISION_SIGN_CROSSROAD,
    K230_VISION_SIGN_PARKING,
    K230_VISION_SIGN_UNKNOWN = 255
} K230VisionSign;

typedef struct {
    int16_t lane_error_x10_px;
    int16_t curvature_x10000;
    uint16_t obstacle_distance_mm;
    K230VisionSign sign;
    uint16_t confidence_x1000;
    uint32_t timestamp_ms;
    uint32_t sequence;
    uint16_t valid;
} K230VisionFrame;

void K230Link_Init(uint32_t now_ms);
void K230Link_SetTransport(const K230LinkTransport *transport);
void K230Link_Update(uint32_t now_ms,
                     uint16_t menu_idle,
                     uint16_t selected_task);
void K230Link_PushRx(K230Byte data, uint32_t now_ms);

void K230Link_RequestPrepare(uint16_t task, uint32_t now_ms);
void K230Link_RequestTask6Center(uint32_t now_ms);
uint16_t K230Link_StartTask(uint16_t task, uint32_t now_ms);
void K230Link_Stop(uint32_t now_ms);

uint16_t K230Link_SendFeedforwardConfig(uint16_t sequence,
                                        uint32_t lead_ms,
                                        uint32_t ramp_ms,
                                        int32_t gain_x100,
                                        int32_t damp_x100,
                                        int16_t max_x10,
                                        int16_t sign);
uint16_t K230Link_SendFeedforwardSample(uint16_t sequence,
                                        int16_t ff_x10,
                                        int16_t reference_accel,
                                        int16_t measured_accel);
uint16_t K230Link_SendFeedforwardEnd(uint16_t sequence);

uint16_t K230Link_IsReady(uint16_t task, uint32_t now_ms);
uint16_t K230Link_IsOnline(uint32_t now_ms);
uint16_t K230Link_ConsumeDone(uint16_t task);
K230LinkState K230Link_GetState(void);
uint16_t K230Link_GetReadyTask(void);
uint16_t K230Link_IsTask6CenterReady(void);
uint16_t K230Link_HasBallPosition(void);
int16_t K230Link_GetBallPositionX10Mm(void);
int16_t K230Link_GetTask6TargetX10Mm(void);
const char *K230Link_GetStatusText(uint32_t now_ms);

/*
 * Smart-car vision frame:
 * [V1,lane_error_x10_px,curvature_x10000,obstacle_mm,sign,confidence_x1000]
 * Example: [V1,-123,450,800,3,950]
 */
uint16_t K230Link_HasVisionFrame(void);
uint16_t K230Link_GetVisionFrame(K230VisionFrame *frame);
uint16_t K230Link_IsVisionFresh(uint32_t now_ms, uint32_t timeout_ms);
uint32_t K230Link_GetRxFrameCount(void);
uint32_t K230Link_GetRxErrorCount(void);

#ifdef __cplusplus
}
#endif

#endif /* K230_LINK_H */
