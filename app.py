# app.py
from flask import Flask, render_template, request, send_file
import os
import pandas as pd
import re
import io
import csv
import logging

app = Flask(__name__)

# Set up logging with absolute path
log_file_path = '/home/mystic/code/vxrail/bandwidth_calculator/app.log'
logging.basicConfig(filename=log_file_path, level=logging.DEBUG)

UPLOAD_FOLDER = '/tmp/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit


class BandwidthCalculator:
    def __init__(self, file_name, vxm_ip, vc_ip):
        self.file_name = file_name
        self.vxm_ip = vxm_ip
        self.vc_ip = vc_ip
        self.df = pd.read_csv(file_name)

    def generate_match_pairs(self):
        vc_services = set()
        clusternodes_services = set()
        for direction in self.df['Direction']:
            if direction.startswith('vc->') or direction.endswith('->vc'):
                service = direction.replace('vc->', '').replace('->vc', '')
                service = re.sub(r'-[a-f0-9]{8,}.*$', '', service)
                vc_services.add(service)
            if direction.startswith('clusternodes->') or direction.endswith('->clusternodes'):
                service = direction.replace('clusternodes->', '').replace('->clusternodes', '')
                service = re.sub(r'-[a-f0-9]{8,}.*$', '', service)
                clusternodes_services.add(service)

        match_pairs = {}
        for service in vc_services:
            key = f'vc_{service}'
            match_pairs[key] = [f'vc.*->.*{service}.*', f'{service}.*->.*vc']

        for service in clusternodes_services:
            key = f'clusternodes_{service}'
            match_pairs[key] = [f'clusternodes.*->.*{service}.*', f'{service}.*->.*clusternodes']

        return match_pairs

    def calculate_bandwidth(self):
        match_pairs = self.generate_match_pairs()
        result = {}
        for pair, match_strings in match_pairs.items():
            total_bandwidth = 0
            for string in match_strings:
                try:
                    matched_rows = self.df[self.df['Direction'].str.contains(string, regex=True)]
                    total_bandwidth += matched_rows['Bandwidth(Kbps)'].sum()
                    total_bandwidth = round(total_bandwidth, 4)
                except Exception as e:
                    print(f'Error occurred: {e}')
            result[pair] = float(total_bandwidth)

        if self.vxm_ip.replace('.', '_') in self.file_name:
            if 'vc_vxm' in result:
                total_other_bandwidth = sum(bw for key, bw in result.items() if key != 'vc_vxm' and not key.startswith('clusternodes'))
                vc_others_bandwidth = result['vc_vxm'] - total_other_bandwidth
                vc_others_bandwidth = round(vc_others_bandwidth, 4)
                result['vc_others'] = vc_others_bandwidth

        return result

def process_files(files, vxm_ip, vc_ip):
    results = []
    for file in files:
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            logging.info(f"Saving file to: {file_path}")
            file.save(file_path)
            logging.info(f"File saved successfully: {file_path}")
            calculator = BandwidthCalculator(file_path, vxm_ip, vc_ip)
            bandwidth = calculator.calculate_bandwidth()
            result = {
                'file_name': file.filename,
                'bandwidth': bandwidth
            }
            results.append(result)
            os.remove(file_path)  # Remove the file after processing
            logging.info(f"File processed and removed: {file_path}")
        except Exception as e:
            logging.error(f"Error processing file {file.filename}: {str(e)}")
    return results

def generate_csv(results, vxm_ip, vc_ip):
    all_keys = set()
    for result in results:
        if result['file_name'].startswith(vc_ip):
            keys = [key for key in result['bandwidth'].keys() if key != 'vc_others' and key != 'clusternodes_vc']
        else:
            keys = [key for key in result['bandwidth'].keys() if key != 'clusternodes_vc']
        all_keys.update(keys)

    sorted_keys = sorted(all_keys)

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    header = ['File Name'] + sorted_keys
    writer.writerow(header)

    # Write data
    for result in results:
        row = [result['file_name']]
        for key in sorted_keys:
            value = result['bandwidth'].get(key, 'N/A')
            row.append(f"{value} Kbps" if isinstance(value, (int, float)) else value)
        writer.writerow(row)

    return output.getvalue()

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        logging.info("POST request received")
        if 'files' not in request.files:
            logging.error("No file part in the request")
            return render_template('index.html', error='No file part')
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            logging.error("No selected file")
            return render_template('index.html', error='No selected file')
        
        vxm_ip = request.form.get('vxm_ip')
        vc_ip = request.form.get('vc_ip')
        
        if not vxm_ip or not vc_ip:
            logging.error("VXM IP or VC IP missing")
            return render_template('index.html', error='VXM IP and VC IP are required')

        logging.info(f"Processing files. VXM IP: {vxm_ip}, VC IP: {vc_ip}")
        results = process_files(files, vxm_ip, vc_ip)
        logging.info(f"Files processed. Results: {results}")
        csv_data = generate_csv(results, vxm_ip, vc_ip)

        return render_template('result.html', results=results, csv_data=csv_data)
    return render_template('index.html')

@app.route('/download_csv', methods=['POST'])
def download_csv():
    csv_data = request.form.get('csv_data')
    if not csv_data:
        logging.error("No CSV data available for download")
        return "No CSV data available", 400

    output = io.StringIO(csv_data)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='bandwidth_results.csv'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)