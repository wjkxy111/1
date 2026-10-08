#ifndef SMART_CAR_ENCODER_SNAPSHOT_H
#define SMART_CAR_ENCODER_SNAPSHOT_H

#include <stdint.h>

#define ENCODER_SNAPSHOT_PERIOD_MS ((uint16_t) 10U)

typedef struct
{
    int32_t left_count;
    int32_t right_count;
    int32_t left_delta_count;
    int32_t right_delta_count;
    int32_t left_counts_per_second;
    int32_t right_counts_per_second;
    uint32_t sequence;
    uint16_t valid;
} EncoderSnapshot;

typedef struct
{
    int32_t previous_left_count;
    int32_t previous_right_count;
    uint32_t sequence;
    uint16_t seeded;
} EncoderSnapshotBuilder;

void EncoderSnapshot_Init(EncoderSnapshotBuilder *builder);
void EncoderSnapshot_Reset(EncoderSnapshotBuilder *builder,
                           int32_t left_count,
                           int32_t right_count);
EncoderSnapshot EncoderSnapshot_Update(EncoderSnapshotBuilder *builder,
                                       int32_t left_count,
                                       int32_t right_count);

#endif
