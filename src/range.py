def get_range_input():
    time_units = ['s', 'ms', 'ps', 'ns', 'µs']
    return {
        'title': 'Display range',
        'value': 100,  # Default value
        'units': time_units
    }