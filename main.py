from flask import Flask, render_template, request, jsonify
import os
import sys
sys.path.append('src')
from file_path import get_directory, browse_directory, get_parent_directory, get_child_directories
from range import get_range_input
from measure import get_dynamic_data
from file import get_file_list

app = Flask(__name__)

@app.route('/')
def index():
    directory = get_directory()
    range_input = get_range_input()
    file_list = get_file_list(directory)
    return render_template('index.html', 
                         title="Microalbumin Rapid Colorimeter",
                         directory=directory,
                         range_input=range_input,
                         file_list=file_list)

@app.route('/browse', methods=['POST'])
def browse():
    new_path = request.form['path']
    if browse_directory(new_path):
        file_list = get_file_list(get_directory())
        return jsonify({'status': 'success', 'path': new_path, 'files': file_list})
    return jsonify({'status': 'error', 'message': 'Invalid directory'})

@app.route('/get_parents', methods=['GET'])
def get_parents():
    current_dir = get_directory()
    parent_dir = get_parent_directory(current_dir)
    return jsonify({'parent': parent_dir})

@app.route('/get_children', methods=['GET'])
def get_children():
    current_dir = get_directory()
    child_dirs = get_child_directories(current_dir)
    return jsonify({'children': child_dirs})

@app.route('/get_data', methods=['GET'])
def get_data():
    selected_file = request.args.get('file')
    range_value = request.args.get('range')
    time_unit = request.args.get('unit')
    print(f"Range value is: {range_value}")
    data = get_dynamic_data(selected_file, range_value, time_unit)
    print(f"Data read is {data}")
    return jsonify(data)

if __name__ == '__main__':
    # For deployment
    # port = int(os.getenv("PORT", 5000))
    # app.run(debug=False, host='0.0.0.0', port=port)

    # For running locally
    app.run(debug=True, port=5001)
