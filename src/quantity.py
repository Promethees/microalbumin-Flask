def get_quantity_input():
    quantities = ['Vmax', 'Slope', 'Saturation', 'Time To Sat']
    return {
        'title': 'Set regressed quantity',
        'quantities': quantities
    }