#include "line_sensor_filter.h"

#define LINE_SENSOR_MASK ((uint16_t) 0x00FFU)

void LineSensorFilter_Init(LineSensorFilter *filter)
{
    if (filter == (LineSensorFilter *) 0)
    {
        return;
    }
    filter->maximum = 3U;
    filter->set_level = 3U;
    filter->clear_level = 0U;
    LineSensorFilter_Reset(filter);
}

void LineSensorFilter_Reset(LineSensorFilter *filter)
{
    uint16_t channel;

    if (filter == (LineSensorFilter *) 0)
    {
        return;
    }
    for (channel = 0U; channel < LINE_SENSOR_CHANNEL_COUNT; channel++)
    {
        filter->level[channel] = 0U;
    }
    filter->filtered_mask = 0U;
    filter->seeded = 0U;
}

uint16_t LineSensorFilter_Update(LineSensorFilter *filter,
                                 uint16_t active_mask)
{
    uint16_t channel;

    if (filter == (LineSensorFilter *) 0)
    {
        return 0U;
    }
    active_mask &= LINE_SENSOR_MASK;
    if (filter->seeded == 0U)
    {
        for (channel = 0U; channel < LINE_SENSOR_CHANNEL_COUNT; channel++)
        {
            uint16_t bit = (uint16_t) (1U << channel);
            filter->level[channel] = ((active_mask & bit) != 0U)
                ? filter->maximum : 0U;
        }
        filter->filtered_mask = active_mask;
        filter->seeded = 1U;
        return filter->filtered_mask;
    }

    for (channel = 0U; channel < LINE_SENSOR_CHANNEL_COUNT; channel++)
    {
        uint16_t bit = (uint16_t) (1U << channel);

        if ((active_mask & bit) != 0U)
        {
            if (filter->level[channel] < filter->maximum)
            {
                filter->level[channel]++;
            }
        }
        else if (filter->level[channel] > 0U)
        {
            filter->level[channel]--;
        }

        if (filter->level[channel] >= filter->set_level)
        {
            filter->filtered_mask |= bit;
        }
        else if (filter->level[channel] <= filter->clear_level)
        {
            filter->filtered_mask &= (uint16_t) ~bit;
        }
    }
    filter->filtered_mask &= LINE_SENSOR_MASK;
    return filter->filtered_mask;
}

uint16_t LineSensorFilter_Count(uint16_t mask)
{
    uint16_t count = 0U;

    mask &= LINE_SENSOR_MASK;
    while (mask != 0U)
    {
        count = (uint16_t) (count + (mask & 1U));
        mask >>= 1U;
    }
    return count;
}

int16_t LineSensorFilter_PositionX10(uint16_t mask)
{
    static const int16_t weights_x10[LINE_SENSOR_CHANNEL_COUNT] =
    {
        350, 240, 140, 50, -50, -140, -240, -350
    };
    int32_t sum = 0;
    uint16_t count;
    uint16_t channel;

    mask &= LINE_SENSOR_MASK;
    count = LineSensorFilter_Count(mask);
    if (count == 0U)
    {
        return 0;
    }
    for (channel = 0U; channel < LINE_SENSOR_CHANNEL_COUNT; channel++)
    {
        if ((mask & (uint16_t) (1U << channel)) != 0U)
        {
            sum += (int32_t) weights_x10[channel];
        }
    }
    return (int16_t) (sum / (int32_t) count);
}
