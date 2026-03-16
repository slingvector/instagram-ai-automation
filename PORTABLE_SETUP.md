# Portable Setup Guide for Instagram AI Automation

## Table of Contents
1. [System Requirements](#system-requirements)
2. [Step-by-Step Setup Instructions](#step-by-step-setup-instructions)
3. [Troubleshooting Guide](#troubleshooting-guide)

## System Requirements
- **Operating System:** Windows 10 or later, macOS Mojave or later, Linux (Ubuntu 20.04 or later)
- **Python Version:** 3.7 or later
- **RAM:** Minimum 8 GB (16 GB recommended)
- **Disk Space:** At least 1 GB of free space
- **Dependencies:**
  - pip
  - required Python libraries (see requirements.txt)

## Step-by-Step Setup Instructions

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/slingvector/instagram-ai-automation.git
   cd instagram-ai-automation
   ```

2. **Switch to the Portable Setup Branch:**
   ```bash
   git checkout portable-setup
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment:**
   - Create a `.env` file in the root directory with your configuration keys.

5. **Run the Application:**
   ```bash
   python main.py
   ```

## Troubleshooting Guide
- **Issue:** Dependencies not found
  - **Solution:** Ensure you are in the correct directory and have installed all dependencies listed in `requirements.txt`.

- **Issue:** Application crashes on startup
  - **Solution:** Check your `.env` configuration for missing or incorrect keys.

- **Issue:** Performance issues
  - **Solution:** Ensure your system meets the recommended RAM requirements and close any unnecessary applications.