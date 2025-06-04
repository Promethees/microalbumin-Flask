def get_range_input():
    time_units = ['seconds', 'milli-sec', 'minutes', 'hours']
    return {
        'title': 'Display range',
        'value': 1000,  # Default value
        'units': time_units
    }