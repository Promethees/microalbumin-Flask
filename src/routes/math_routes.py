from flask import Blueprint, jsonify
from validators import validate_json
from math_ops import calculate_coef_and_rsquared, calculate_kinetics_quantities, evaluate_curve

math_bp = Blueprint('math', __name__)

@math_bp.route('/calculate_coef_and_rsquared', methods=['POST'])
@validate_json({
    'x': (list, [], True),
    'y': (list, [], True),
    'regress_algo': (str, 'linear', False)
})
def calc_coef_rsquared(validated_data):
    try:
        x = validated_data['x']
        y = validated_data['y']
        algo = validated_data['regress_algo']
        
        result = calculate_coef_and_rsquared(x, y, algo)
        return jsonify({'status': 'success', 'result': result})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@math_bp.route('/calculate_kinetics_quantities', methods=['POST'])
@validate_json({
    'XColumn': (list, [], True),
    'YColumn': (list, [], True),
    'window_size': (int, 4, True)
})
def calc_kinetics(validated_data):
    try:
        x_col = validated_data['XColumn']
        y_col = validated_data['YColumn']
        window_size = validated_data['window_size']
        
        result = calculate_kinetics_quantities(x_col, y_col, window_size)
        return jsonify({'status': 'success', 'result': result})
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500

@math_bp.route('/calculate_concentration', methods=['POST'])
@validate_json({
    'regress_algo': (str, 'linear', False),
    'coefficients': ((dict, list), None, True),
    'x': ((int, float, str), None, True),
})
def calc_concentration(validated_data):
    """Quick standalone calculator: given a curve's coefficients and a measured
    quantity value ``x``, return the derived concentration — no CSV data file
    required. Mirrors the applied-curve math (evaluate_curve / excel_formula)."""
    try:
        algo = validated_data['regress_algo']
        coefficients = validated_data['coefficients']
        x_raw = validated_data['x']
        try:
            x = float(x_raw)
        except (TypeError, ValueError):
            return jsonify({'status': 'failure', 'message': 'Measured value must be a number'}), 400

        concentration = evaluate_curve(algo, coefficients, x)
        if concentration != concentration or concentration in (float('inf'), float('-inf')):
            return jsonify({'status': 'failure', 'message': 'Result is not a finite number for this input'}), 400
        return jsonify({'status': 'success', 'concentration': float(concentration)})
    except ValueError as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500
