#include "encoder_snapshot.h"

#include <limits.h>

static int32_t EncoderSnapshot_ClampDelta(int64_t value)
{
    if (value > (int64_t) INT32_MAX)
    {
        return INT32_MAX;
    }
    if (value < (int64_t) INT32_MIN)
    {
        return INT32_MIN;
    }
    return (int32_t) value;
}

void EncoderSnapshot_Init(EncoderSnapshotBuilder *builder)
{
    if (builder == (EncoderSnapshotBuilder *) 0)
    {
        return;
    }
    builder->previous_left_count = 0;
    builder->previous_right_count = 0;
    builder->sequence = 0U;
    builder->seeded = 0U;
}

void EncoderSnapshot_Reset(EncoderSnapshotBuilder *builder,
                           int32_t left_count,
                           int32_t right_count)
{
    if (builder == (EncoderSnapshotBuilder *) 0)
    {
        return;
    }
    builder->previous_left_count = left_count;
    builder->previous_right_count = right_count;
    builder->sequence = 0U;
    builder->seeded = 1U;
}

EncoderSnapshot EncoderSnapshot_Update(EncoderSnapshotBuilder *builder,
                                       int32_t left_count,
                                       int32_t right_count)
{
    EncoderSnapshot snapshot = {0};

    snapshot.left_count = left_count;
    snapshot.right_count = right_count;
    if (builder == (EncoderSnapshotBuilder *) 0)
    {
        return snapshot;
    }

    if (builder->seeded == 0U)
    {
        EncoderSnapshot_Reset(builder, left_count, right_count);
        return snapshot;
    }

    snapshot.left_delta_count = EncoderSnapshot_ClampDelta(
        (int64_t) left_count - (int64_t) builder->previous_left_count);
    snapshot.right_delta_count = EncoderSnapshot_ClampDelta(
        (int64_t) right_count - (int64_t) builder->previous_right_count);
    snapshot.left_counts_per_second = EncoderSnapshot_ClampDelta(
        (int64_t) snapshot.left_delta_count * (int64_t) 100);
    snapshot.right_counts_per_second = EncoderSnapshot_ClampDelta(
        (int64_t) snapshot.right_delta_count * (int64_t) 100);

    builder->previous_left_count = left_count;
    builder->previous_right_count = right_count;
    builder->sequence++;
    snapshot.sequence = builder->sequence;
    snapshot.valid = 1U;
    return snapshot;
}
