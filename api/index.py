import os
import sys
import io
import base64
import time
from flask import Flask, request, jsonify, render_template_string
from PIL import Image
from pypdf import PdfReader, PdfWriter, PageObject, Transformation
from reportlab.pdfgen import canvas

app = Flask(__name__)

# ==============================================================================
# CONFIGURATION
# ==============================================================================
MERCHANT_UPI = "omkar.chaudhari7087@okhdfcbank"
MERCHANT_NAME = "Campus PrintFlow"
KIOSK_NAME = "Campus Express Print"

GLOBAL_JOBS = []
token_counter = 1

def convert_to_pdf_bytes(file_bytes, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext == 'pdf':
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            return file_bytes, len(reader.pages)
        except Exception:
            return file_bytes, 1
    elif ext in ['jpg', 'jpeg', 'png', 'bmp', 'webp']:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            out_io = io.BytesIO()
            img.save(out_io, "PDF", resolution=100.0)
            return out_io.getvalue(), 1
        except Exception:
            return file_bytes, 1
    return file_bytes, 1

def apply_nup_and_stamp(pdf_bytes, nup_mode, doc_type, token_str, student_name, roll_no):
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
        a4_w, a4_h = 595.28, 841.89
        writer = PdfWriter()

        if nup_mode == 1:
            for page in reader.pages:
                writer.add_page(page)
        elif nup_mode == 2:
            scale = 0.68
            for i in range(0, total_pages, 2):
                new_page = PageObject.create_blank_page(width=a4_w, height=a4_h)
                p1 = reader.pages[i]
                tx1 = (a4_w - float(p1.mediabox.width) * scale) / 2
                ty1 = (a4_h / 2) + ((a4_h / 2) - float(p1.mediabox.height) * scale) / 2
                p1.add_transformation(Transformation().scale(scale).translate(tx1, ty1))
                new_page.merge_page(p1)

                if i + 1 < total_pages:
                    p2 = reader.pages[i + 1]
                    tx2 = (a4_w - float(p2.mediabox.width) * scale) / 2
                    ty2 = ((a4_h / 2) - float(p2.mediabox.height) * scale) / 2
                    p2.add_transformation(Transformation().scale(scale).translate(tx2, ty2))
                    new_page.merge_page(p2)
                writer.add_page(new_page)

        elif nup_mode == 4:
            scale = 0.48
            for i in range(0, total_pages, 4):
                new_page = PageObject.create_blank_page(width=a4_w, height=a4_h)
                positions = [
                    (15, (a4_h / 2) + 15),
                    ((a4_w / 2) + 10, (a4_h / 2) + 15),
                    (15, 15),
                    ((a4_w / 2) + 10, 15)
                ]
                for slot in range(4):
                    if i + slot < total_pages:
                        p = reader.pages[i + slot]
                        tx, ty = positions[slot]
                        p.add_transformation(Transformation().scale(scale).translate(tx, ty))
                        new_page.merge_page(p)
                writer.add_page(new_page)

        if doc_type != 'confidential' and len(writer.pages) > 0:
            first_p = writer.pages[0]
            pw = float(first_p.mediabox.width)
            ph = float(first_p.mediabox.height)

            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(pw, ph))
            can.setFont("Helvetica-Bold", 8)
            can.setFillColorRGB(0.2, 0.2, 0.2)
            u_info = f" | {student_name} ({roll_no})" if student_name else ""
            can.drawRightString(pw - 20, ph - 15, f"Token: {token_str}{u_info} | PrintFlow")
            can.save()
            packet.seek(0)
            
            w_pdf = PdfReader(packet)
            first_p.merge_page(w_pdf.pages[0])

        out_stream = io.BytesIO()
        writer.write(out_stream)
        return out_stream.getvalue()
    except Exception:
        return pdf_bytes

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>PrintFlow - Kiosk</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: #f1f5f9; color: #0f172a; display: flex; justify-content: center; min-height: 100vh; }
        .app-shell { width: 100%; max-width: 420px; background: #ffffff; min-height: 100vh; display: flex; flex-direction: column; position: relative; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }
        .top-nav { background: #004d40; color: #ffffff; padding: 14px 18px; display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #ff9900; }
        .user-greeting { font-size: 13px; font-weight: 700; color: #fef08a; }
        .history-btn { background: rgba(255,255,255,0.15); color: #ffffff; border: none; padding: 6px 12px; border-radius: 8px; font-size: 11px; font-weight: 700; cursor: pointer; }
        .screen { display: none; padding: 18px; flex: 1; flex-direction: column; justify-content: space-between; }
        .screen.active { display: flex; }
        .login-logo { width: 60px; height: 60px; background: #e6f4f1; border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 30px; margin: 20px auto 12px; }
        .input-group { text-align: left; margin-bottom: 12px; }
        .input-group label { display: block; font-size: 12px; font-weight: 700; color: #334155; margin-bottom: 5px; }
        .input-box { width: 100%; padding: 12px; border: 1.5px solid #cbd5e1; border-radius: 10px; font-size: 14px; font-weight: 600; outline: none; }
        .sec-title { font-size: 13px; font-weight: 800; color: #0f172a; margin-bottom: 8px; }
        .doc-type-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
        .doc-type-card { border: 2px solid #e2e8f0; border-radius: 10px; padding: 10px; text-align: center; cursor: pointer; background: #f8fafc; }
        .doc-type-card.active { border-color: #004d40; background: #e6f4f1; }
        .doc-type-badge { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 4px; margin-top: 3px; display: inline-block; }
        .badge-assign { background: #e0f2fe; color: #0284c7; }
        .badge-conf { background: #fef2f2; color: #dc2626; }
        .upload-card { border: 2px dashed #00796b; border-radius: 12px; background: #fafdfc; padding: 16px; text-align: center; cursor: pointer; }
        .preview-wrapper { background: #0f172a; border-radius: 10px; margin-top: 10px; overflow: hidden; display: none; }
        .preview-frame { width: 100%; height: 200px; border: none; background: #fff; }
        .nup-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 6px; }
        .nup-card { background: #fff; border: 1.5px solid #cbd5e1; border-radius: 8px; padding: 6px; text-align: center; cursor: pointer; }
        .nup-card.active { border-color: #004d40; background: #e6f4f1; }
        .nup-badge { font-size: 8px; background: #15803d; color: #fff; padding: 1px 4px; border-radius: 4px; font-weight: 700; }
        .config-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 8px 12px; margin-top: 10px; }
        .config-row { display: flex; align-items: center; justify-content: space-between; padding: 5px 0; font-size: 12px; font-weight: 700; }
        .pill-group { display: flex; background: #e2e8f0; padding: 2px; border-radius: 6px; }
        .pill { border: none; background: transparent; padding: 4px 8px; border-radius: 5px; font-size: 11px; font-weight: 700; color: #64748b; cursor: pointer; }
        .pill.active { background: #004d40; color: #fff; }
        .counter-btn { width: 24px; height: 24px; border-radius: 5px; border: 1px solid #cbd5e1; background: #fff; font-weight: 800; cursor: pointer; }
        .bill-card { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 10px; padding: 8px 12px; font-size: 12px; margin-top: 8px; }
        .bill-row { display: flex; justify-content: space-between; margin-bottom: 3px; color: #64748b; }
        .bill-total { display: flex; justify-content: space-between; font-size: 14px; font-weight: 800; color: #004d40; border-top: 1px solid #e5e7eb; padding-top: 4px; }
        .btn-amazon { background: #ff9900; color: #0f172a; border: none; padding: 13px; border-radius: 10px; font-size: 14px; font-weight: 800; width: 100%; cursor: pointer; margin-top: 10px; }
        .btn-amazon:disabled { background: #94a3b8; cursor: not-allowed; }
        .upi-app-btn { background: #004d40; color: white; border-radius: 10px; padding: 11px; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 800; text-decoration: none; margin-top: 10px; }
        .qr-card { background: #fff; border: 1.5px solid #e2e8f0; border-radius: 10px; padding: 10px; text-align: center; margin-top: 10px; }
        #qrcode { display: flex; justify-content: center; margin: 6px 0; }
        .tracker-box { background: #004d40; color: white; border-radius: 12px; padding: 20px; text-align: center; margin-top: 15px; }
        .token-num { font-size: 44px; font-weight: 900; color: #fef08a; margin: 4px 0; }
    </style>
</head>
<body>
    <div class="app-shell">
        <div class="top-nav">
            <div>
                <span style="font-weight: 800; font-size: 14px;">🖨️ {{ kiosk_name }}</span>
                <div class="user-greeting" id="navUserGreeting">Student Guest</div>
            </div>
            <button class="history-btn" onclick="openHistoryScreen()">📜 My Prints</button>
        </div>

        <!-- SCREEN 0: LOGIN -->
        <div id="screen-0" class="screen active">
            <div style="text-align: center;">
                <div class="login-logo">🎓</div>
                <h2 style="font-size: 18px; font-weight: 800;">Student Access</h2>
                <p style="font-size: 12px; color: #64748b; margin-top: 4px;">Enter details to stamp on your assignments</p>
                <div style="margin-top: 18px;">
                    <div class="input-group">
                        <label>Full Name *</label>
                        <input type="text" id="studName" class="input-box" placeholder="e.g. Rahul Sharma">
                    </div>
                    <div class="input-group">
                        <label>Roll Number *</label>
                        <input type="text" id="studRoll" class="input-box" placeholder="e.g. 21CO045">
                    </div>
                </div>
            </div>
            <button class="btn-amazon" onclick="saveProfile()">Continue to Kiosk ❯</button>
        </div>

        <!-- SCREEN 1: UPLOAD & CONFIG -->
        <div id="screen-1" class="screen">
            <div>
                <div class="sec-title">1. Document Type</div>
                <div class="doc-type-grid">
                    <div class="doc-type-card active" id="dt-assign" onclick="setDocType('assignment')">
                        <div style="font-size: 18px;">🎓</div>
                        <div style="font-size: 11px; font-weight: 800;">College Work</div>
                        <div class="doc-type-badge badge-assign">Header ON</div>
                    </div>
                    <div class="doc-type-card" id="dt-conf" onclick="setDocType('confidential')">
                        <div style="font-size: 18px;">🔒</div>
                        <div style="font-size: 11px; font-weight: 800;">Confidential</div>
                        <div class="doc-type-badge badge-conf">No Watermark</div>
                    </div>
                </div>

                <div class="sec-title">2. Choose Document</div>
                <div class="upload-card" onclick="document.getElementById('fileInp').click()">
                    <div style="font-size: 20px;">📂</div>
                    <div style="font-size: 12px; font-weight: 800; color: #004d40;" id="upText">Tap to Select File</div>
                </div>
                <input type="file" id="fileInp" accept=".pdf,image/*" onchange="fileSelected(this)" style="display: none;">

                <div class="preview-wrapper" id="previewContainer">
                    <iframe id="pdfFrame" class="preview-frame"></iframe>
                </div>

                <div class="sec-title" style="margin-top: 10px;">3. Pages per Sheet</div>
                <div class="nup-grid">
                    <div class="nup-card active" id="nup-1" onclick="setNup(1)">
                        <div style="font-size: 11px; font-weight: 800;">1-in-1</div>
                    </div>
                    <div class="nup-card" id="nup-2" onclick="setNup(2)">
                        <div style="font-size: 11px; font-weight: 800;">2-in-1</div>
                        <div class="nup-badge">Save 50%</div>
                    </div>
                    <div class="nup-card" id="nup-4" onclick="setNup(4)">
                        <div style="font-size: 11px; font-weight: 800;">4-in-1</div>
                        <div class="nup-badge">Save 75%</div>
                    </div>
                </div>

                <div class="config-card">
                    <div class="config-row">
                        <span>Color</span>
                        <div class="pill-group">
                            <button class="pill active" id="c-bw" onclick="setColor('bw')">B&W</button>
                            <button class="pill" id="c-col" onclick="setColor('col')">Color</button>
                        </div>
                    </div>
                    <div class="config-row">
                        <span>Sides</span>
                        <div class="pill-group">
                            <button class="pill active" id="s-sin" onclick="setSide('sin')">Single</button>
                            <button class="pill" id="s-dbl" onclick="setSide('dbl')">2-Sided</button>
                        </div>
                    </div>
                    <div class="config-row">
                        <span>Copies</span>
                        <div style="display: flex; gap: 6px; align-items: center;">
                            <button class="counter-btn" onclick="addCopies(-1)">-</button>
                            <span id="cpVal" style="font-weight: 800;">1</span>
                            <button class="counter-btn" onclick="addCopies(1)">+</button>
                        </div>
                    </div>
                </div>

                <div class="bill-card">
                    <div class="bill-row"><span>Sheets</span><span id="billSheets">1 Sheets</span></div>
                    <div class="bill-total"><span>Total</span><span id="billTotal">₹2.00</span></div>
                </div>
            </div>
            <button class="btn-amazon" id="btnPay" disabled onclick="goPayment()">Proceed to Pay ❯</button>
        </div>

        <!-- SCREEN 2: PAYMENT -->
        <div id="screen-2" class="screen">
            <div>
                <button onclick="go(1)" style="border:none;background:none;font-size:18px;cursor:pointer;">← Back</button>
                <a id="genericUpiBtn" href="#" class="upi-app-btn" onclick="paidDone()">
                    ⚡ Pay via GooglePay / PhonePe
                </a>
                <div class="qr-card">
                    <div style="font-size: 11px; font-weight: 700; color: #64748b;">SCAN QR TO PAY</div>
                    <div id="qrcode"></div>
                    <div style="font-size: 18px; font-weight: 900; color: #004d40;" id="qrTotal">₹2.00</div>
                    <button onclick="paidDone()" style="background:#f0fdf4;border:1px dashed #15803d;color:#15803d;padding:8px;border-radius:6px;width:100%;margin-top:6px;font-weight:700;">
                        ✓ Paid via QR? Click to Print
                    </button>
                </div>
            </div>
            <button class="btn-amazon" id="btnConfirm" disabled onclick="submitPrint()">🔒 Complete Payment to Print</button>
        </div>

        <!-- SCREEN 3: TOKEN -->
        <div id="screen-3" class="screen">
            <div>
                <div class="tracker-box">
                    <div style="font-size: 12px; opacity: 0.9;">Assigned Token</div>
                    <div class="token-num" id="tokDisp">A-01</div>
                    <div style="font-size: 12px; color: #a7f3d0;">✓ Sent to Local Printer!</div>
                </div>
                <p style="text-align: center; color: #64748b; font-size: 12px; margin-top: 14px;">
                    Collect your physical pages from the printer tray.
                </p>
            </div>
            <button class="btn-amazon" onclick="location.reload()">Print Another 🔄</button>
        </div>

        <!-- SCREEN 4: HISTORY -->
        <div id="screen-4" class="screen">
            <div>
                <button onclick="go(1)" style="border:none;background:none;font-size:18px;cursor:pointer;">← Back</button>
                <h3 style="font-size: 16px; font-weight: 800; margin: 12px 0;">📜 Print History</h3>
                <div id="histList" style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;"></div>
            </div>
            <button class="btn-amazon" onclick="go(1)">Back to Kiosk ❯</button>
        </div>
    </div>

    <script>
        const UPI_ID = "{{ upi_id }}";
        const MERCHANT_NAME = "{{ merchant_name }}";
        let currentStudent = null;
        let selectedDocType = 'assignment';
        let fileRawBase64 = null;
        let fileName = "";
        let pages = 1;
        let nup = 1;
        let copies = 1;
        let color = 'bw';
        let side = 'sin';
        let total = 2;

        window.onload = function() {
            const u = localStorage.getItem('pflow_u');
            if(u) {
                currentStudent = JSON.parse(u);
                document.getElementById('navUserGreeting').innerText = `Hi, ${currentStudent.name.split(' ')[0]} 👋`;
                go(1);
            }
        };

        function saveProfile() {
            const name = document.getElementById('studName').value.trim();
            const roll = document.getElementById('studRoll').value.trim();
            if(!name || !roll) return alert("Enter Name and Roll No");
            currentStudent = { name, roll };
            localStorage.setItem('pflow_u', JSON.stringify(currentStudent));
            document.getElementById('navUserGreeting').innerText = `Hi, ${name.split(' ')[0]} 👋`;
            go(1);
        }

        function go(n) {
            for(let i=0; i<=4; i++) {
                const el = document.getElementById('screen-' + i);
                if(el) el.classList.remove('active');
            }
            document.getElementById('screen-' + n).classList.add('active');
        }

        function setDocType(t) {
            selectedDocType = t;
            document.getElementById('dt-assign').className = t==='assignment' ? 'doc-type-card active' : 'doc-type-card';
            document.getElementById('dt-conf').className = t==='confidential' ? 'doc-type-card active' : 'doc-type-card';
        }

        function fileSelected(inp) {
            if(inp.files && inp.files[0]) {
                const f = inp.files[0];
                fileName = f.name;
                document.getElementById('upText').innerText = "Selected: " + f.name;
                const reader = new FileReader();
                reader.onload = function(e) {
                    fileRawBase64 = e.target.result.split(',')[1];
                    document.getElementById('previewContainer').style.display = 'block';
                    document.getElementById('pdfFrame').src = e.target.result;
                    document.getElementById('btnPay').removeAttribute('disabled');
                    calc();
                };
                reader.readAsDataURL(f);
            }
        }

        function setNup(n) {
            nup = n;
            [1,2,4].forEach(x => document.getElementById('nup-'+x).className = (x===n)?'nup-card active':'nup-card');
            calc();
        }
        function setColor(c) {
            color = c;
            document.getElementById('c-bw').className = c==='bw'?'pill active':'pill';
            document.getElementById('c-col').className = c==='col'?'pill active':'pill';
            calc();
        }
        function setSide(s) {
            side = s;
            document.getElementById('s-sin').className = s==='sin'?'pill active':'pill';
            document.getElementById('s-dbl').className = s==='dbl'?'pill active':'pill';
            calc();
        }
        function addCopies(n) {
            copies = Math.max(1, copies + n);
            document.getElementById('cpVal').innerText = copies;
            calc();
        }

        function calc() {
            let finalSheets = Math.ceil(pages / nup);
            let rate = (color === 'bw') ? (side === 'dbl' ? 1.50 : 2.00) : 10.00;
            total = Math.max(1, finalSheets * copies * rate);
            document.getElementById('billSheets').innerText = `${finalSheets} Sheets (${nup}-in-1)`;
            document.getElementById('billTotal').innerText = '₹' + total.toFixed(2);
        }

        function goPayment() {
            document.getElementById('qrTotal').innerText = '₹' + total.toFixed(2);
            const upi = `upi://pay?pa=${encodeURIComponent(UPI_ID)}&pn=${encodeURIComponent(MERCHANT_NAME)}&am=${total}&cu=INR&tn=PrintFlow`;
            document.getElementById('genericUpiBtn').href = upi;
            const q = document.getElementById('qrcode');
            q.innerHTML = "";
            new QRCode(q, { text: upi, width: 120, height: 120 });
            go(2);
        }

        function paidDone() {
            const b = document.getElementById('btnConfirm');
            b.removeAttribute('disabled');
            b.innerText = "✅ Paid • Send to Printer";
            b.style.background = "#004d40";
        }

        async function submitPrint() {
            const b = document.getElementById('btnConfirm');
            b.disabled = true;
            b.innerText = "⏳ Routing via Vercel...";

            try {
                const response = await fetch('/api/enqueue', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_base64: fileRawBase64,
                        filename: fileName,
                        doc_type: selectedDocType,
                        nup: nup,
                        copies: copies,
                        student_name: currentStudent ? currentStudent.name : '',
                        roll_no: currentStudent ? currentStudent.roll : ''
                    })
                });

                const d = await response.json();
                if(d.status === 'success') {
                    let hist = [];
                    try { hist = JSON.parse(localStorage.getItem('pflow_history')) || []; } catch(e){}
                    const now = new Date();
                    hist.unshift({
                        token: d.token,
                        filename: fileName,
                        date: now.toLocaleDateString() + ' ' + now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}),
                        pages: Math.ceil(pages/nup),
                        copies: copies,
                        cost: total.toFixed(2)
                    });
                    localStorage.setItem('pflow_history', JSON.stringify(hist));

                    document.getElementById('tokDisp').innerText = d.token;
                    go(3);
                } else {
                    alert("Error: " + (d.message || "Failed"));
                    b.disabled = false;
                    b.innerText = "🔒 Complete Payment to Print";
                }
            } catch (err) {
                alert("Network error: " + err.message);
                b.disabled = false;
                b.innerText = "🔒 Complete Payment to Print";
            }
        }

        function openHistoryScreen() {
            const listEl = document.getElementById('histList');
            let hist = [];
            try {
                hist = JSON.parse(localStorage.getItem('pflow_history')) || [];
            } catch(e) { hist = []; }
            
            if(!hist || hist.length === 0) {
                listEl.innerHTML = `
                    <div style="text-align: center; color: #64748b; padding: 40px 10px; font-size: 13px; background: #f8fafc; border-radius: 12px; border: 1.5px dashed #cbd5e1;">
                        <div style="font-size: 28px; margin-bottom: 8px;">📑</div>
                        <strong>No print history yet.</strong>
                    </div>`;
            } else {
                listEl.innerHTML = hist.map(h => `
                    <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 10px; padding: 12px; margin-bottom: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="background: #e6f4f1; color: #004d40; font-weight: 800; font-size: 11px; padding: 2px 8px; border-radius: 4px;">Token ${h.token || 'A-01'}</span>
                            <span style="font-size: 11px; color: #64748b;">${h.date || 'Today'}</span>
                        </div>
                        <div style="font-size: 13px; font-weight: 700; color: #0f172a; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">📄 ${h.filename || 'Document'}</div>
                        <div style="font-size: 11px; color: #64748b; display: flex; justify-content: space-between; border-top: 1px dashed #e2e8f0; padding-top: 6px; margin-top: 4px;">
                            <span>${h.pages || 1} Sheets • ${h.copies || 1} Copy</span>
                            <span style="font-weight: 800; color: #004d40; font-size: 12px;">₹${h.cost || '2.00'}</span>
                        </div>
                    </div>
                `).join('');
            }
            go(4);
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE, upi_id=MERCHANT_UPI, merchant_name=MERCHANT_NAME, kiosk_name=KIOSK_NAME)

@app.route('/api/enqueue', methods=['POST'])
def enqueue():
    global token_counter
    try:
        data = request.json or {}
        raw_b64 = data.get('file_base64')
        if not raw_b64:
            return jsonify({'status': 'error', 'message': 'No file received'}), 400

        filename = data.get('filename', 'doc.pdf')
        doc_type = data.get('doc_type', 'assignment')
        nup = int(data.get('nup', 1))
        copies = int(data.get('copies', 1))
        student_name = data.get('student_name', '')
        roll_no = data.get('roll_no', '')

        token = f"A-{token_counter:02d}"
        token_counter += 1

        file_bytes = base64.b64decode(raw_b64)
        pdf_bytes, pages = convert_to_pdf_bytes(file_bytes, filename)
        final_pdf_bytes = apply_nup_and_stamp(pdf_bytes, nup, doc_type, token, student_name, roll_no)

        GLOBAL_JOBS.append({
            'token': token,
            'filename': filename,
            'pdf_base64': base64.b64encode(final_pdf_bytes).decode('utf-8'),
            'student_name': student_name,
            'roll_no': roll_no,
            'doc_type': doc_type,
            'copies': copies,
            'time': time.time()
        })

        return jsonify({'status': 'success', 'token': token})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get-pending-jobs', methods=['GET'])
def get_pending_jobs():
    return jsonify({'jobs': GLOBAL_JOBS})

@app.route('/api/mark-job-done', methods=['POST'])
def mark_job_done():
    global GLOBAL_JOBS
    token = request.json.get('token')
    GLOBAL_JOBS = [j for j in GLOBAL_JOBS if j.get('token') != token]
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)