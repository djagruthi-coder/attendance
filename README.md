# 🎓 Smart Attendance Monitoring System

## 📌 Overview
This project is a web-based attendance management system designed for colleges.  
It allows teachers to manage attendance efficiently and students to track their performance with alerts and analytics.

---

## 🚀 Features

### 👨‍🎓 Student
- Login using Roll Number & DOB
- View overall attendance percentage
- Subject-wise attendance table
- Pie chart & bar chart visualization
- Low attendance popup alert (<80%)
- Email notification for low attendance

### 👨‍🏫 Teacher
- Login as teacher
- Select class (Branch & Section)
- Mark attendance using checkbox table
- Bulk attendance submission
- View all students' attendance
- Add new students dynamically

---

## 🧠 Key Concepts Used
- Role-Based Access Control (Student / Teacher)
- Attendance percentage calculation
- Threshold-based alert system
- Bulk data processing
- Data aggregation
- Email notification system

---

## 🛠️ Technologies Used
- **Backend:** Python (Flask)
- **Database:** SQLite
- **Frontend:** HTML, CSS, JavaScript
- **Charts:** Chart.js

---

## ⚙️ How It Works

1. User logs in (Student / Teacher)
2. Teacher marks attendance for class
3. Data is stored in SQLite database
4. System calculates attendance percentage
5. Alerts are generated based on thresholds
6. Student dashboard displays analytics
7. Email is sent if attendance < 80%

---

## 📊 Alert System
- 🔴 < 75% → Critical
- 🟠 < 85% → Warning
- 🟢 ≥ 85% → Safe

---

## 🗄️ Database Structure

### Students Table
- roll_no
- name
- dob
- branch
- section
- role

### Attendance Records Table
- roll_no
- subject
- attended
- total

---
