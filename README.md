# Face Recognition Attendance System
**Mutah University - Faculty of Information Technology**  
*Graduation Project (2026)*

## About the Project
The Face Recognition Attendance System is an intelligent, automated attendance management prototype designed specifically for university classroom environments. The system replaces traditional paper-based lists and manual roll-calls with a real-time, camera-driven facial recognition mechanism using computer vision and deep learning technologies.

### Key Features:
* **Real-Time Facial Recognition:** Uses YOLOv11m-face for precise face detection and DeepFace/FaceNet for facial embedding extraction and matching.
* **Multi-Frame Confirmation:** Implements a 4-consecutive-frame threshold mechanism to eliminate false positives and ensure accurate attendance logging.
* **Role-Based Access Control (RBAC):** Separate interfaces and permissions for Administrators, Instructors, and Students.
* **Automated Session Management:** Instructors can start/end lecture sessions, and the system automatically links attendance records to the correct course section.
* **Excuse Management:** Students can upload absence excuses (e.g., medical reports), which instructors can review, approve, or reject.

## Project Team
* **Rama Issam AL-Sawadha** (Computer Science)
* **Rahaf Sufian Alazzeh** (Computer Science)
* **Sara Amin ALMaagbeh** (Information Security and Digital Forensics)
* **Jana Raed Al-Dalaeen** (Information Security and Digital Forensics)
* **Aya Naser Al-shamaileh** (Computer Information Systems)

**Supervisor:** Dr. Anas Al-Kasasbeh

## Technology Stack
* **Backend:** Python, Flask
* **Database:** MySQL 8.0, phpMyAdmin
* **AI & Computer Vision:** OpenCV, YOLOv11m-face, DeepFace, FaceNet
* **Frontend:** HTML5, CSS3, JavaScript, Jinja2
* **Deployment:** Docker & Docker Compose

