from flask import Blueprint, jsonify
from app.services.job_service import JobService

jobs_bp = Blueprint('jobs', __name__)

@jobs_bp.route('/api/jobs', methods=['GET'])
def get_all_jobs():
    js = JobService()
    jobs = [job.to_dict() for job in js.get_all_jobs()]
    return jsonify(jobs)

@jobs_bp.route('/api/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    js = JobService()
    job = js.get_job(job_id)
    if not job:
        return jsonify({"success": False, "error": "Job nao encontrado"}), 404
    return jsonify(job.to_dict())
