from models import Notification

def send_notification(user, title, message, notification_type='claim_update', 
                     priority='medium', link=None):
    """Send notification to user"""
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        priority=priority,
        link=link
    )


def alert_suspicious_activity(user, bill, reason):
    """Alert for suspicious bill activity"""
    return send_notification(
        user=user,
        title="⚠️ Suspicious Activity Detected",
        message=f"Bill from {bill.hospital_name} (₹{bill.total_amount}) has been flagged for: {reason}",
        notification_type='suspicious',
        priority='high',
        link=f"/bills/{bill.id}/"
    )


def notify_claim_update(claim, status):
    """Notify user about claim status change"""
    messages = {
        'approved': f"Your claim #{claim.id} has been APPROVED! Expected payout: ₹{claim.claim_amount}",
        'rejected': f"Your claim #{claim.id} was REJECTED. Reason: {claim.rejection_reason}",
        'review': "Your claim is under review by the insurance company.",
    }
    
    return send_notification(
        user=claim.patient,
        title=f"Claim {status.upper()}",
        message=messages.get(status.lower(), f"Claim status updated to {status}"),
        notification_type='claim_update',
        priority='high' if status in ['approved', 'rejected'] else 'medium',
        link=f"/claims/"
    )


def send_recommendation(user, title, message, link=None):
    """Send AI recommendations"""
    return send_notification(
        user=user,
        title=title,
        message=message,
        notification_type='recommendation',
        priority='medium',
        link=link
    )