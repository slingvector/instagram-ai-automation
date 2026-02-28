import os
from flask import Flask, request, jsonify
import logging
from controllers.factory_controller import process_job

# Set up standard logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/", methods=["POST"])
def index():
    """
    HTTP entry point for the Cloud Run instance.
    Expects a POST payload containing 'job_id'.
    """
    request_json = request.get_json(silent=True)
    if not request_json or 'job_id' not in request_json:
        logger.error("Invalid Request: Missing 'job_id' in payload.")
        return jsonify({"error": "Bad Request: Missing 'job_id'"}), 400
        
    job_id = request_json['job_id']
    logger.info(f"Received processing request for Job ID: {job_id}")
    
    return process_job(job_id)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
