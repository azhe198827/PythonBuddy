"""Created originally by Ethan Chiu 10/25/16
v2.0.0 created on 8/4/18
Complete redesign for efficiency and scalability
Uses Python 3 now

v2.1.0 created on 5/10/19
Improve efficiency and design
 """
from flask import Response, Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO
import eventlet.wsgi
import tempfile, mmap, os, re
from datetime import datetime
from pylint import epylint as lint
from subprocess import Popen, PIPE, STDOUT
from multiprocessing import Pool, cpu_count
import base64
import config
import time
import hashlib


def is_os_linux():
    if os.name == "nt":
        return False
    return True


# Configure Flask App
# Remember to change the SECRET_KEY!
app = Flask(__name__, static_url_path='/nb/static')
app.config['SECRET_KEY'] = 'secret!'
app.config['DEBUG'] = True
socketio = SocketIO(app)

# Get number of cores for multiprocessing
num_cores = cpu_count()


def check_sign():
    timestamp = request.headers.get('timestamp')
    signature = request.headers.get('signature')
    staffid = request.headers.get('staffid')
    staffname = request.headers.get('staffname')
    x_rio_seq = request.headers.get('x-rio-seq')
    x_ext_data = request.headers.get('x-ext-data')

    if not (timestamp or signature or staffid or staffname or x_rio_seq):
        return 'tof request missing param'

    # 不许超过180秒
    if int(time.time()) - int(timestamp) > 180:
        return 'timestamp check failure'

    params = (timestamp + config.tof_token + x_rio_seq + ',' + staffid +
              ',' + staffname + ',' + x_ext_data + timestamp).encode('utf-8')

    # 验签
    computer_signature = hashlib.sha256(params).hexdigest().upper()
    if computer_signature != signature:
        return 'signature failure'

    return None


def get_username():
    return request.headers.get('staffname')


@app.route('/')
def index():
    """Display home page
        :return: index.html

        Initializes session variables for tracking time between running code.
    """
    session["count"] = 0
    session["time_now"] = datetime.now()
    return render_template("index.html")


@app.route('/nb/error')
def error():
    error_msg = request.args.get("error_msg")
    if not error_msg:
        error_msg = '发生错误'
    return render_template("error.html", error_msg=error_msg)


@app.route('/nb/<username>/<notebook>')
def user_notebook(username, notebook):
    check_ret = check_sign()
    if check_ret is not None:
        return redirect(url_for('error', error_msg=check_ret))
    visitor = get_username()

    readonly = bool(request.args.get('readonly'))

    session["count"] = 0
    session["time_now"] = datetime.now()
    notebook_path = '%s/notebook/%s/%s.py' % (config.quant_dir, username, notebook)
    if not os.path.exists(notebook_path):
        return redirect(url_for('error'))

    modify_time = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(notebook_path)))

    notebook_content = ''
    with open(notebook_path) as n:
        notebook_content = n.read()

    return render_template("index.html", notebook_content=notebook_content,
                           modify_time=modify_time, readonly=str(visitor != username or readonly))


@app.route('/nb/image', methods=['post', 'get'])
def image():
    path = "/Users/mingzhepan/github/PythonBuddy/PythonBuddy/static/image/a.png"

    resp = Response(open(path, 'rb'), mimetype="image/jpeg")
    return resp


# Run python in secure system


def return_img_stream(img_local_path):
    img_local_path = "/Users/mingzhepan/github/PythonBuddy/PythonBuddy/static/image/a.png"
    import base64
    img_stream = ''
    with open(img_local_path, 'r') as img_f:
        img_stream = img_f.read()
        img_stream = base64.b64encode(img_stream)
    return img_stream


@app.route('/nb/save_code', methods=['POST'])
def save_code():
    check_ret = check_sign()
    if check_ret is not None:
        return redirect(url_for('error', error_msg=check_ret))
    visitor = get_username()

    text = request.form['text']
    username = request.form['username']
    notebook = request.form['notebook']

    if visitor != username:
        return

    notebook_path = '%s/notebook/%s/%s.py' % (config.quant_dir, username, notebook)
    with open(notebook_path, 'w') as n:
        n.write(text)


@app.route('/nb/check_result', methods=['POST'])
def check_result():
    check_ret = check_sign()
    if check_ret is not None:
        return redirect(url_for('error', error_msg=check_ret))
    ioa_name = request.form['username']
    notebook = request.form['notebook']
    ioa_root_path = '/data/quant/notebook/' + ioa_name + '/'

    output_path = '%s/output.log' % ioa_root_path
    image_path = '%s/%s.png' % (ioa_root_path, notebook)
    if not os.path.exists(output_path):
        return jsonify({})
    if not os.path.exists(image_path):
        return jsonify({})

    output = ''
    with open(output_path, 'r') as f:
        output = f.read()

    image = ''
    with open(image_path, 'rb') as f:
        image = base64.b64encode(f.read())

    return jsonify({0: output, 1: image})


@app.route('/nb/run_code', methods=['POST'])
def run_code():
    check_ret = check_sign()
    if check_ret is not None:
        return redirect(url_for('error', error_msg=check_ret))
    session["code"] = request.form['text']
    username = request.form['username']
    notebook = request.form['notebook']
    text = session["code"]
    session["file_name"] = username
    # try:
    #    session["file_name"]
    #    f = open(session["file_name"], "w")
    #    for t in text:
    #        f.write(t)
    #    f.flush()
    #    f.close()
    # except KeyError as e:
    #    with tempfile.NamedTemporaryFile(delete=False) as temp:
    #        session["file_name"] = temp.name
    #        for t in text:
    #            temp.write(t.encode("utf-8"))
    #        temp.flush()
    #        temp.close()
    print("start")
    if slow():
        print("/run_code exit slow")
        return jsonify({
            0: "Running code too much within a short time period. Please wait a few seconds before clicking \"Run\" each time.",
            1: ""})
    session["time_now"] = datetime.now()

    output = None
    if 1:
        ioa_name = username  # session["file_name"]
        ioa_root_path = '/data/quant/notebook/' + ioa_name + '/'
        cmd = 'mkdir -p ' + ioa_root_path
        os.system(cmd)
        cmd = 'cp /data/third.tar ' + ioa_root_path
        os.system(cmd)
        cmd = 'tar -xvf ' + ioa_root_path + 'third.tar -C ' + ioa_root_path
        os.system(cmd)
        file_start = open(ioa_root_path + '/start', 'rb').read()
        file_end = open(ioa_root_path + '/end', 'rb').read()
        file_new = open(ioa_root_path + '/run', 'wb')
        config_data = "\nconfig['mod']['sys_analyser']['output_file'] = '%s/%s.pickle'\n" % (ioa_root_path, notebook) + \
                      "config['mod']['sys_analyser']['plot_save_file'] = '%s/%s.png'\n" % (ioa_root_path, notebook)
        file_new.write(file_start)
        for t in text:
            file_new.write(t.encode('utf-8'))
        file_new.write(config_data.encode('utf-8'))
        file_new.write(file_end)
        file_new.close()
        cmd = 'python3 ' + ioa_root_path + '/run'

        p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE,
                  stderr=STDOUT, close_fds=True)
        output = p.stdout.read()
        # 写入日志，下次读取
        with open('%s/output.log' % ioa_root_path, 'w') as o:
            o.write(output.decode('utf-8'))
        image_path = ioa_root_path + '/' + notebook + '.png'
        if os.path.exists(image_path):
            f = open(image_path, 'rb')
            image = base64.b64encode(f.read())
            return jsonify({0: output.decode('utf-8'), 1: image})
        else:
            return jsonify({0: output.decode('utf-8'), 1: ''})
    else:
        cmd = 'python3 ' + session["file_name"]

        p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE,
                  stderr=STDOUT, close_fds=True)
        output = p.stdout.read()
        path = '/Users/mingzhepan/github/PythonBuddy/image/a.png'
        f = open(path, 'rb')
        image = base64.b64encode(f.read())
        return jsonify({0: output.decode('utf-8'), 1: image})


# Slow down if user clicks "Run" too many times
def slow():
    session["count"] += 1
    time = datetime.now() - session["time_now"]
    if float(session["count"]) / float(time.total_seconds()) > 5:
        return True
    return False


def remove_temp_code_file():
    os.remove(session["file_name"])


@socketio.on('disconnect', namespace='/check_disconnect')
def disconnect():
    print("disconnetct")
    pass


if __name__ == "__main__":
    """Initialize app"""
    socketio.run(app)
