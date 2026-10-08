#ifndef SMART_CAR_LINE_SENSOR_FILTER_H
#define SMART_CAR_LINE_SENSOR_FILTER_H

#include <stdint.h>

#define LINE_SENSOR_CHANNEL_COUNT ((uint16_t) 8U)

typedef struct
{
    uint16_t level[LINE_SENSOR_CHANNEL_COUNT];
    uint16_t maximum;
    uint16_t set_level;
    uint16_t clear_level;
    uint16_t filtered_mask;
    uint16_t seeded;
} LineSensorFilter;

void LineSensorFilter_Init(LineSensorFilter *filter);
void LineSensorFilter_Reset(LineSensorFilter *filter);
uint16_t LineSensorFilter_Update(LineSensorFilter *filter,
                                 uint16_t active_mask);
uint16_t LineSensorFilter_Count(uint16_t mask);
int16_t LineSensorFilter_PositionX10(uint16_t mask);

#endif
