# نسخة بايثون خفيفة
FROM python:3.9-slim

# مكان العمل جوا الحاوية
WORKDIR /app

# انسخ كل الملفات
COPY . .

# أمر وهمي عشان الحاوية تضل شغالة وما تطفي
CMD ["python", "-c", "import time; print('AI Service Started...'); [time.sleep(60) for _ in range(100)]"]