import time
import requests
import os
import tempfile
import subprocess
import sys
import base64

# ==============================================================================
# Vercel Deployment ची तुमची लाईव्ह लिंक इथे टाका:
# ==============================================================================
VERCEL_URL = "https://your-project-name.vercel.app"  # <-- तुमची Vercel URL

print("==================================================")
print("🚀 PrintFlow Vercel Hardware Bridge चालू आहे...")
print(f"📡 Vercel Endpoint: {VERCEL_URL}")
print("🖨️ लॅपटॉपचा प्रिंटर ऑर्डर घेण्यासाठी सज्ज आहे!")
print("==================================================")

while True:
    try:
        res = requests.get(f"{VERCEL_URL}/api/get-pending-jobs", timeout=10)
        if res.status_code == 200:
            data = res.json()
            jobs = data.get('jobs', [])

            for job in jobs:
                token = job['token']
                filename = job['filename']
                student = job.get('student_name', 'Student')
                doc_type = job.get('doc_type', 'assignment')
                pdf_b64 = job.get('pdf_base64')

                print(f"\n📥 नवीन प्रिंट मिळाली! Token: {token} | User: {student} | Mode: {doc_type}")

                # Base64 मधून थेट PDF फाईल तयार करणे
                pdf_bytes = base64.b64decode(pdf_b64)
                local_path = os.path.join(tempfile.gettempdir(), f"print_{token}_{filename}.pdf")
                with open(local_path, "wb") as f:
                    f.write(pdf_bytes)

                # प्रिंटरमधून कागद काढणे
                print(f"🖨️ प्रिंटरमधून कागद बाहेर काढत आहे...")
                if sys.platform.startswith('win'):
                    try:
                        import win32api
                        win32api.ShellExecute(0, "print", local_path, None, ".", 0)
                    except Exception:
                        subprocess.run(f'powershell -Command "Start-Process -FilePath \'{local_path}\' -Verb Print"', shell=True)
                else:
                    subprocess.run(['lp', local_path], check=False)

                # Vercel ला कळवणे की जॉब पूर्ण झाला
                requests.post(f"{VERCEL_URL}/api/mark-job-done", json={'token': token}, timeout=5)
                print(f"✅ Token {token} यशस्वीरीत्या प्रिंट झाला!")
                time.sleep(2)

    except Exception:
        pass

    time.sleep(3)