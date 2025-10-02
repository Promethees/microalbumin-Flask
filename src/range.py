def get_range_input():
    time_units = ['seconds', 'minutes', 'hours']
    return {
        'title': 'Display range',
        'value_start': 0,  # Default value
        'value_end': 1000,  # Default value
        'units': time_units
    }