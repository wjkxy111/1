#include "k230_link.h"

#define K230_FRAME_PAYLOAD_MAX       (95U)
#define K230_TX_FRAME_MAX            (95U)
#define K230_PENDING_COMMAND_MAX     (8U)
#define K230_COMMAND_RETRY_MS        (200U)
#define K230_ONLINE_TIMEOUT_MS       (500U)
#define K230_POLL_BUDGET             (128U)

typedef enum {
    K230_PENDING_NONE = 0,
    K230_PENDING_PREPARE,
    K230_PENDING_CENTER_TASK6,
    K230_PENDING_START,
    K230_PENDING_STOP
} K230PendingType;

static K230LinkTransport s_transport;
static K230LinkState s_state;
static K230PendingType s_pending_type;
static uint16_t s_pending_task;
static K230Byte s_pending_command[K230_PENDING_COMMAND_MAX];
static uint16_t s_pending_length;
static uint32_t s_last_command_ms;

static uint16_t s_seen_rx;
static uint32_t s_last_rx_ms;
static uint16_t s_ready_task;
static uint16_t s_done_flags;
static uint16_t s_task6_center_ready;
static int16_t s_task6_target_x10_mm;
static int16_t s_ball_position_x10_mm;
static uint16_t s_ball_position_valid;

static K230Byte s_rx_payload[K230_FRAME_PAYLOAD_MAX];
static uint16_t s_rx_length;
static uint16_t s_rx_in_frame;
static uint32_t s_rx_frame_count;
static uint32_t s_rx_error_count;
static K230VisionFrame s_vision;

static uint16_t IsTaskControlled(uint16_t task)
{
    return ((task >= 3U) && (task <= 6U)) ? 1U : 0U;
}

static K230Byte Byte(char value)
{
    return (K230Byte)((uint16_t)value & 0x00FFU);
}

static uint16_t IsByte(K230Byte value, char expected)
{
    return (((uint16_t)value & 0x00FFU) ==
            ((uint16_t)expected & 0x00FFU)) ? 1U : 0U;
}

static uint16_t PayloadEquals(const K230Byte *payload,
                              uint16_t length,
                              const char *literal)
{
    uint16_t index = 0U;

    if ((payload == 0) || (literal == 0)) return 0U;
    while (literal[index] != '\0') {
        if ((index >= length) ||
            (((uint16_t)payload[index] & 0x00FFU) !=
             ((uint16_t)literal[index] & 0x00FFU))) return 0U;
        index++;
    }
    return (index == length) ? 1U : 0U;
}

static uint16_t TransportWrite(const K230Byte *data, uint16_t length)
{
    if ((s_transport.write == 0) || (data == 0) || (length == 0U)) {
        return 0U;
    }
    return s_transport.write(s_transport.context, data, length) ? 1U : 0U;
}

static uint16_t AppendByte(K230Byte *buffer, uint16_t capacity,
                           uint16_t *length, K230Byte value)
{
    if ((buffer == 0) || (length == 0) || (*length >= capacity)) return 0U;
    buffer[*length] = (K230Byte)((uint16_t)value & 0x00FFU);
    (*length)++;
    return 1U;
}

static uint16_t AppendUnsigned(K230Byte *buffer, uint16_t capacity,
                               uint16_t *length, uint32_t value)
{
    K230Byte reversed[10];
    uint16_t digits = 0U;

    do {
        reversed[digits++] = (K230Byte)('0' + (value % 10U));
        value /= 10U;
    } while ((value != 0U) && (digits < 10U));
    while (digits != 0U) {
        digits--;
        if (!AppendByte(buffer, capacity, length, reversed[digits])) return 0U;
    }
    return 1U;
}

static uint16_t AppendSigned(K230Byte *buffer, uint16_t capacity,
                             uint16_t *length, int32_t value)
{
    uint32_t magnitude;

    if (value < 0) {
        if (!AppendByte(buffer, capacity, length, Byte('-'))) return 0U;
        magnitude = (uint32_t)(-(value + 1L)) + 1U;
    } else {
        magnitude = (uint32_t)value;
    }
    return AppendUnsigned(buffer, capacity, length, magnitude);
}

static uint16_t SendFeedforward(char subtype,
                                const int32_t *values,
                                uint16_t count)
{
    K230Byte frame[K230_TX_FRAME_MAX];
    uint16_t length = 0U;
    uint16_t index;

    if ((values == 0) || (count == 0U)) return 0U;
    if (!AppendByte(frame, K230_TX_FRAME_MAX, &length, Byte('[')) ||
        !AppendByte(frame, K230_TX_FRAME_MAX, &length, Byte('F')) ||
        !AppendByte(frame, K230_TX_FRAME_MAX, &length, Byte(subtype))) return 0U;
    for (index = 0U; index < count; index++) {
        if (!AppendByte(frame, K230_TX_FRAME_MAX, &length, Byte(',')) ||
            !AppendSigned(frame, K230_TX_FRAME_MAX, &length, values[index])) {
            return 0U;
        }
    }
    if (!AppendByte(frame, K230_TX_FRAME_MAX, &length, Byte(']'))) return 0U;
    return TransportWrite(frame, length);
}

uint16_t K230Link_SendFeedforwardConfig(uint16_t sequence,
                                        uint32_t lead_ms,
                                        uint32_t ramp_ms,
                                        int32_t gain_x100,
                                        int32_t damp_x100,
                                        int16_t max_x10,
                                        int16_t sign)
{
    int32_t values[7];

    if ((lead_ms > 2147483647UL) || (ramp_ms > 2147483647UL)) return 0U;
    values[0] = (int32_t)sequence;
    values[1] = (int32_t)lead_ms;
    values[2] = (int32_t)ramp_ms;
    values[3] = gain_x100;
    values[4] = damp_x100;
    values[5] = (int32_t)max_x10;
    values[6] = (sign < 0) ? -1L : 1L;
    return SendFeedforward('C', values, 7U);
}

uint16_t K230Link_SendFeedforwardSample(uint16_t sequence,
                                        int16_t ff_x10,
                                        int16_t reference_accel,
                                        int16_t measured_accel)
{
    int32_t values[4];
    values[0] = (int32_t)sequence;
    values[1] = (int32_t)ff_x10;
    values[2] = (int32_t)reference_accel;
    values[3] = (int32_t)measured_accel;
    return SendFeedforward('A', values, 4U);
}

uint16_t K230Link_SendFeedforwardEnd(uint16_t sequence)
{
    int32_t value = (int32_t)sequence;
    return SendFeedforward('E', &value, 1U);
}

static uint16_t ParseDigit(K230Byte value, uint16_t *digit)
{
    uint16_t octet = (uint16_t)value & 0x00FFU;
    if ((digit == 0) || (octet < (uint16_t)'0') ||
        (octet > (uint16_t)'9')) return 0U;
    *digit = octet - (uint16_t)'0';
    return 1U;
}

static uint16_t ParseFixedSigned(const K230Byte *text,
                                 uint16_t digits,
                                 int16_t *value)
{
    int32_t magnitude = 0;
    uint16_t index;
    uint16_t digit;

    if ((text == 0) || (value == 0) ||
        (!IsByte(text[0], '+') && !IsByte(text[0], '-'))) return 0U;
    for (index = 0U; index < digits; index++) {
        if (!ParseDigit(text[index + 1U], &digit)) return 0U;
        magnitude = magnitude * 10L + (int32_t)digit;
    }
    if (magnitude > 32767L) return 0U;
    *value = IsByte(text[0], '-') ? (int16_t)(-magnitude) : (int16_t)magnitude;
    return 1U;
}

static uint16_t ParseInteger(const K230Byte *text, uint16_t length,
                             int32_t minimum, int32_t maximum,
                             int32_t *value)
{
    uint16_t index = 0U;
    uint16_t negative = 0U;
    uint16_t digit;
    uint32_t magnitude = 0U;
    uint32_t limit;
    int32_t parsed;

    if ((text == 0) || (value == 0) || (length == 0U)) return 0U;
    if (IsByte(text[index], '-')) { negative = 1U; index++; }
    else if (IsByte(text[index], '+')) index++;
    if (index >= length) return 0U;
    limit = negative ? 2147483648UL : 2147483647UL;
    while (index < length) {
        if (!ParseDigit(text[index], &digit)) return 0U;
        if (magnitude > ((limit - (uint32_t)digit) / 10U)) return 0U;
        magnitude = magnitude * 10U + (uint32_t)digit;
        index++;
    }
    if (negative) {
        parsed = (magnitude == 2147483648UL)
            ? (-2147483647L - 1L) : -(int32_t)magnitude;
    } else parsed = (int32_t)magnitude;
    if ((parsed < minimum) || (parsed > maximum)) return 0U;
    *value = parsed;
    return 1U;
}

static uint16_t SplitCsv(const K230Byte *payload, uint16_t length,
                         const K230Byte **fields, uint16_t *field_lengths,
                         uint16_t capacity)
{
    uint16_t count = 0U;
    uint16_t start = 0U;
    uint16_t index;

    if ((payload == 0) || (fields == 0) || (field_lengths == 0) ||
        (capacity == 0U) || (length == 0U)) return 0U;
    for (index = 0U; index <= length; index++) {
        if ((index == length) || IsByte(payload[index], ',')) {
            if ((count >= capacity) || (index == start)) return 0U;
            fields[count] = &payload[start];
            field_lengths[count] = index - start;
            count++;
            start = index + 1U;
        }
    }
    return count;
}

static void ClearPending(void)
{
    s_pending_type = K230_PENDING_NONE;
    s_pending_task = 0U;
    s_pending_length = 0U;
}

static uint16_t QueueCommand(const K230Byte *command, uint16_t length,
                             K230PendingType type, uint16_t task,
                             uint32_t now_ms)
{
    uint16_t index;

    if ((command == 0) || (length == 0U) ||
        (length > K230_PENDING_COMMAND_MAX)) return 0U;
    for (index = 0U; index < length; index++) {
        s_pending_command[index] = (K230Byte)((uint16_t)command[index] & 0x00FFU);
    }
    s_pending_length = length;
    s_pending_type = type;
    s_pending_task = task;
    s_last_command_ms = now_ms;
    if (TransportWrite(s_pending_command, s_pending_length)) return 1U;
    s_last_command_ms = now_ms - K230_COMMAND_RETRY_MS;
    return 0U;
}

static void QueueTaskCommand(char prefix, uint16_t task,
                             K230PendingType type, uint32_t now_ms)
{
    K230Byte command[4];
    if (!IsTaskControlled(task)) return;
    command[0] = Byte('[');
    command[1] = Byte(prefix);
    command[2] = (K230Byte)((uint16_t)'0' + task);
    command[3] = Byte(']');
    (void)QueueCommand(command, 4U, type, task, now_ms);
}

static void SetReady(uint16_t task)
{
    if (!IsTaskControlled(task)) return;
    s_ready_task = task;
    s_state = K230_LINK_STATE_READY;
    if ((s_pending_type == K230_PENDING_PREPARE) &&
        (s_pending_task == task)) ClearPending();
}

static void HandleNumericPayload(const K230Byte *payload, uint16_t length)
{
    int16_t value;

    /* Legacy K230 position: [+0123*], in 0.1 mm. */
    if ((length != 6U) || !IsByte(payload[5], '*') ||
        !ParseFixedSigned(payload, 4U, &value)) {
        s_rx_error_count++;
        return;
    }
    if (value == 9999) s_ball_position_valid = 0U;
    else if (value == 9998) s_done_flags |= (uint16_t)(1U << 3U);
    else {
        s_ball_position_x10_mm = value;
        s_ball_position_valid = 1U;
    }
}

static uint16_t HandleVisionPayload(const K230Byte *payload,
                                    uint16_t length,
                                    uint32_t now_ms)
{
    const K230Byte *fields[6];
    uint16_t field_lengths[6];
    int32_t values[5];
    uint16_t count;
    uint16_t index;

    if ((length < 3U) || !IsByte(payload[0], 'V') ||
        !IsByte(payload[1], '1') || !IsByte(payload[2], ',')) return 0U;
    count = SplitCsv(payload, length, fields, field_lengths, 6U);
    if ((count != 6U) || (field_lengths[0] != 2U) ||
        !IsByte(fields[0][0], 'V') || !IsByte(fields[0][1], '1')) {
        s_rx_error_count++;
        return 1U;
    }
    for (index = 0U; index < 5U; index++) {
        int32_t minimum = 0L;
        int32_t maximum = 65535L;
        if ((index == 0U) || (index == 1U)) {
            minimum = -32767L; maximum = 32767L;
        } else if (index == 3U) maximum = 255L;
        else if (index == 4U) maximum = 1000L;
        if (!ParseInteger(fields[index + 1U], field_lengths[index + 1U],
                          minimum, maximum, &values[index])) {
            s_rx_error_count++;
            return 1U;
        }
    }
    s_vision.lane_error_x10_px = (int16_t)values[0];
    s_vision.curvature_x10000 = (int16_t)values[1];
    s_vision.obstacle_distance_mm = (uint16_t)values[2];
    s_vision.sign = (values[3] <= (int32_t)K230_VISION_SIGN_PARKING)
        ? (K230VisionSign)values[3] : K230_VISION_SIGN_UNKNOWN;
    s_vision.confidence_x1000 = (uint16_t)values[4];
    s_vision.timestamp_ms = now_ms;
    s_vision.sequence++;
    s_vision.valid = 1U;
    return 1U;
}

static void HandlePayload(const K230Byte *payload,
                          uint16_t length,
                          uint32_t now_ms)
{
    uint16_t task;
    int16_t target;

    if ((payload == 0) || (length == 0U)) {
        s_rx_error_count++;
        return;
    }
    s_seen_rx = 1U;
    if (HandleVisionPayload(payload, length, now_ms)) return;
    if ((IsByte(payload[0], '+') || IsByte(payload[0], '-')) &&
        (length == 6U)) {
        HandleNumericPayload(payload, length);
        return;
    }
    if ((length == 2U) && IsByte(payload[0], 'R') &&
        (((uint16_t)payload[1] & 0x00FFU) >= (uint16_t)'3') &&
        (((uint16_t)payload[1] & 0x00FFU) <= (uint16_t)'6')) {
        task = ((uint16_t)payload[1] & 0x00FFU) - (uint16_t)'0';
        SetReady(task);
        return;
    }
    if ((length == 8U) && IsByte(payload[0], 'R') &&
        IsByte(payload[1], '6') && IsByte(payload[2], ',') &&
        ParseFixedSigned(&payload[3], 4U, &target)) {
        s_task6_target_x10_mm = target;
        SetReady(6U);
        return;
    }
    if ((length == 8U) && IsByte(payload[0], 'L') &&
        IsByte(payload[1], '6') && IsByte(payload[2], ',') &&
        ParseFixedSigned(&payload[3], 4U, &target)) {
        s_task6_target_x10_mm = target;
        s_ready_task = 0U;
        s_state = K230_LINK_STATE_LOCKING_TASK6;
        return;
    }
    if (PayloadEquals(payload, length, "C6OK")) {
        s_task6_center_ready = 1U;
        s_ready_task = 0U;
        s_state = K230_LINK_STATE_IDLE;
        if (s_pending_type == K230_PENDING_CENTER_TASK6) ClearPending();
        return;
    }
    if ((length == 5U) && IsByte(payload[0], 'P') &&
        IsByte(payload[1], 'R') && IsByte(payload[2], 'E') &&
        IsByte(payload[3], 'P') &&
        (((uint16_t)payload[4] & 0x00FFU) >= (uint16_t)'3') &&
        (((uint16_t)payload[4] & 0x00FFU) <= (uint16_t)'5')) {
        task = ((uint16_t)payload[4] & 0x00FFU) - (uint16_t)'0';
        if ((s_pending_type == K230_PENDING_PREPARE) &&
            (s_pending_task == task)) s_state = K230_LINK_STATE_PREPARING;
        return;
    }
    if (PayloadEquals(payload, length, "CENTER6")) {
        if (s_pending_type == K230_PENDING_CENTER_TASK6)
            s_state = K230_LINK_STATE_CENTERING_TASK6;
        return;
    }
    if (PayloadEquals(payload, length, "SET6")) {
        s_state = K230_LINK_STATE_SETTING_TASK6;
        return;
    }
    if ((length == 4U) && IsByte(payload[0], 'R') &&
        IsByte(payload[1], 'U') && IsByte(payload[2], 'N') &&
        (((uint16_t)payload[3] & 0x00FFU) >= (uint16_t)'3') &&
        (((uint16_t)payload[3] & 0x00FFU) <= (uint16_t)'6')) {
        task = ((uint16_t)payload[3] & 0x00FFU) - (uint16_t)'0';
        s_ready_task = 0U;
        s_state = K230_LINK_STATE_RUNNING;
        if ((s_pending_type == K230_PENDING_START) &&
            (s_pending_task == task)) ClearPending();
        return;
    }
    if ((length == 2U) && IsByte(payload[0], 'D') &&
        (((uint16_t)payload[1] & 0x00FFU) >= (uint16_t)'3') &&
        (((uint16_t)payload[1] & 0x00FFU) <= (uint16_t)'6')) {
        task = ((uint16_t)payload[1] & 0x00FFU) - (uint16_t)'0';
        s_done_flags |= (uint16_t)(1U << task);
        return;
    }
    if (PayloadEquals(payload, length, "RETURN")) {
        s_state = K230_LINK_STATE_RETURNING;
        return;
    }
    if (PayloadEquals(payload, length, "IDLE")) {
        s_state = K230_LINK_STATE_IDLE;
        s_ready_task = 0U;
        if (s_pending_type == K230_PENDING_STOP) ClearPending();
        return;
    }
    if ((length >= 3U) && IsByte(payload[0], 'E') &&
        IsByte(payload[1], 'R') && IsByte(payload[2], 'R')) {
        s_state = K230_LINK_STATE_ERROR;
        ClearPending();
        return;
    }
    s_rx_error_count++;
}

void K230Link_PushRx(K230Byte data, uint32_t now_ms)
{
    K230Byte octet = (K230Byte)((uint16_t)data & 0x00FFU);

    if (IsByte(octet, '[')) {
        s_rx_in_frame = 1U;
        s_rx_length = 0U;
        return;
    }
    if (!s_rx_in_frame) return;
    if (IsByte(octet, ']')) {
        s_last_rx_ms = now_ms;
        s_rx_frame_count++;
        HandlePayload(s_rx_payload, s_rx_length, now_ms);
        s_rx_in_frame = 0U;
        s_rx_length = 0U;
        return;
    }
    if (s_rx_length < K230_FRAME_PAYLOAD_MAX) {
        s_rx_payload[s_rx_length++] = octet;
    } else {
        s_rx_in_frame = 0U;
        s_rx_length = 0U;
        s_rx_error_count++;
    }
}

static void ProcessRx(uint32_t now_ms)
{
    K230Byte data;
    uint16_t count = 0U;

    if (s_transport.read_byte == 0) return;
    while ((count < K230_POLL_BUDGET) &&
           s_transport.read_byte(s_transport.context, &data)) {
        K230Link_PushRx((K230Byte)((uint16_t)data & 0x00FFU), now_ms);
        count++;
    }
}

static void RetryPending(uint32_t now_ms)
{
    if ((s_pending_type != K230_PENDING_NONE) &&
        ((uint32_t)(now_ms - s_last_command_ms) >= K230_COMMAND_RETRY_MS)) {
        if (TransportWrite(s_pending_command, s_pending_length))
            s_last_command_ms = now_ms;
    }
}

void K230Link_SetTransport(const K230LinkTransport *transport)
{
    if (transport == 0) {
        s_transport.read_byte = 0;
        s_transport.write = 0;
        s_transport.context = 0;
    } else s_transport = *transport;
}

void K230Link_Init(uint32_t now_ms)
{
    s_state = K230_LINK_STATE_OFFLINE;
    s_pending_type = K230_PENDING_NONE;
    s_pending_task = 0U;
    s_pending_length = 0U;
    s_last_command_ms = now_ms;
    s_seen_rx = 0U;
    s_last_rx_ms = now_ms;
    s_ready_task = 0U;
    s_done_flags = 0U;
    s_task6_center_ready = 0U;
    s_task6_target_x10_mm = 0;
    s_ball_position_x10_mm = 0;
    s_ball_position_valid = 0U;
    s_rx_length = 0U;
    s_rx_in_frame = 0U;
    s_rx_frame_count = 0U;
    s_rx_error_count = 0U;
    s_vision.lane_error_x10_px = 0;
    s_vision.curvature_x10000 = 0;
    s_vision.obstacle_distance_mm = 0U;
    s_vision.sign = K230_VISION_SIGN_NONE;
    s_vision.confidence_x1000 = 0U;
    s_vision.timestamp_ms = now_ms;
    s_vision.sequence = 0U;
    s_vision.valid = 0U;
}

void K230Link_Update(uint32_t now_ms,
                     uint16_t menu_idle,
                     uint16_t selected_task)
{
    (void)menu_idle;
    (void)selected_task;
    ProcessRx(now_ms);
    RetryPending(now_ms);
    if (!K230Link_IsOnline(now_ms) &&
        (s_state != K230_LINK_STATE_PREPARING) &&
        (s_state != K230_LINK_STATE_CENTERING_TASK6) &&
        (s_state != K230_LINK_STATE_SETTING_TASK6) &&
        (s_state != K230_LINK_STATE_LOCKING_TASK6)) {
        s_ready_task = 0U;
        s_state = K230_LINK_STATE_OFFLINE;
    }
}

void K230Link_RequestPrepare(uint16_t task, uint32_t now_ms)
{
    if (!IsTaskControlled(task)) return;
    if ((s_ready_task == task) && K230Link_IsOnline(now_ms)) return;
    if ((s_pending_type == K230_PENDING_PREPARE) &&
        (s_pending_task == task)) return;
    s_ready_task = 0U;
    if (task == 6U) {
        s_task6_center_ready = 0U;
        s_state = K230_LINK_STATE_SETTING_TASK6;
    } else s_state = K230_LINK_STATE_PREPARING;
    QueueTaskCommand('P', task, K230_PENDING_PREPARE, now_ms);
}

void K230Link_RequestTask6Center(uint32_t now_ms)
{
    K230Byte command[4];
    if (s_pending_type == K230_PENDING_CENTER_TASK6) return;
    s_ready_task = 0U;
    s_task6_center_ready = 0U;
    s_state = K230_LINK_STATE_CENTERING_TASK6;
    command[0] = Byte('['); command[1] = Byte('C');
    command[2] = Byte('6'); command[3] = Byte(']');
    (void)QueueCommand(command, 4U, K230_PENDING_CENTER_TASK6, 6U, now_ms);
}

uint16_t K230Link_StartTask(uint16_t task, uint32_t now_ms)
{
    if (!IsTaskControlled(task) || !K230Link_IsReady(task, now_ms)) return 0U;
    s_done_flags &= (uint16_t)~(1U << task);
    s_ready_task = 0U;
    s_state = K230_LINK_STATE_RUNNING;
    QueueTaskCommand('G', task, K230_PENDING_START, now_ms);
    return 1U;
}

void K230Link_Stop(uint32_t now_ms)
{
    K230Byte command[3];
    s_ready_task = 0U;
    s_task6_center_ready = 0U;
    s_state = K230_LINK_STATE_RETURNING;
    command[0] = Byte('['); command[1] = Byte('S'); command[2] = Byte(']');
    (void)QueueCommand(command, 3U, K230_PENDING_STOP, 0U, now_ms);
}

uint16_t K230Link_IsReady(uint16_t task, uint32_t now_ms)
{
    return ((s_ready_task == task) && K230Link_IsOnline(now_ms)) ? 1U : 0U;
}

uint16_t K230Link_IsOnline(uint32_t now_ms)
{
    if (!s_seen_rx) return 0U;
    return ((uint32_t)(now_ms - s_last_rx_ms) <= K230_ONLINE_TIMEOUT_MS)
        ? 1U : 0U;
}

uint16_t K230Link_ConsumeDone(uint16_t task)
{
    uint16_t mask;
    if (task > 15U) return 0U;
    mask = (uint16_t)(1U << task);
    if ((s_done_flags & mask) == 0U) return 0U;
    s_done_flags &= (uint16_t)~mask;
    return 1U;
}

K230LinkState K230Link_GetState(void) { return s_state; }
uint16_t K230Link_GetReadyTask(void) { return s_ready_task; }
uint16_t K230Link_IsTask6CenterReady(void) { return s_task6_center_ready; }
uint16_t K230Link_HasBallPosition(void) { return s_ball_position_valid; }
int16_t K230Link_GetBallPositionX10Mm(void) { return s_ball_position_x10_mm; }
int16_t K230Link_GetTask6TargetX10Mm(void) { return s_task6_target_x10_mm; }
uint16_t K230Link_HasVisionFrame(void) { return s_vision.valid; }

uint16_t K230Link_GetVisionFrame(K230VisionFrame *frame)
{
    if ((frame == 0) || !s_vision.valid) return 0U;
    *frame = s_vision;
    return 1U;
}

uint16_t K230Link_IsVisionFresh(uint32_t now_ms, uint32_t timeout_ms)
{
    return (s_vision.valid &&
            ((uint32_t)(now_ms - s_vision.timestamp_ms) <= timeout_ms))
        ? 1U : 0U;
}

uint32_t K230Link_GetRxFrameCount(void) { return s_rx_frame_count; }
uint32_t K230Link_GetRxErrorCount(void) { return s_rx_error_count; }

const char *K230Link_GetStatusText(uint32_t now_ms)
{
    if (!K230Link_IsOnline(now_ms)) return "K230:OFFLINE";
    switch (s_state) {
        case K230_LINK_STATE_IDLE: return "K230:IDLE";
        case K230_LINK_STATE_PREPARING: return "K230:PREPARING";
        case K230_LINK_STATE_CENTERING_TASK6: return "K230:CENTERING";
        case K230_LINK_STATE_SETTING_TASK6: return "K230:SET TARGET";
        case K230_LINK_STATE_LOCKING_TASK6: return "K230:T6 LOCKING";
        case K230_LINK_STATE_READY:
            switch (s_ready_task) {
                case 3U: return "K230:T3 READY";
                case 4U: return "K230:T4 READY";
                case 5U: return "K230:T5 READY";
                case 6U: return "K230:T6 READY";
                default: return "K230:READY";
            }
        case K230_LINK_STATE_RUNNING: return "K230:RUNNING";
        case K230_LINK_STATE_RETURNING: return "K230:RETURNING";
        case K230_LINK_STATE_ERROR: return "K230:ERROR";
        case K230_LINK_STATE_OFFLINE:
        default: return "K230:OFFLINE";
    }
}
