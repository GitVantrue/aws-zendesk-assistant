# HTML Report Generation Fixes - December 12, 2025

## Issues Fixed

### 1. CloudWatch Alarms Data Structure Mismatch
**Problem**: The code was trying to access `cw_data.get('alarms', [])` expecting a list, but the actual structure has `alarms` as a dictionary with `details` key containing the list.

**Error**: `AttributeError: 'str' object has no attribute 'get'`

**Solution**: 
- Modified the CloudWatch data processing to check if `alarms` is a dictionary
- Extract the `details` list from the dictionary structure
- Also extract summary statistics from the dictionary

**Code Changes**:
```python
# Before
'cloudwatch_alarm_rows': generate_cloudwatch_rows(cw_data.get('alarms', [])),

# After
cw_alarms = cw_data.get('alarms', {})
if isinstance(cw_alarms, dict):
    cw_alarms_list = cw_alarms.get('details', [])
    cw_summary = {
        'total': cw_alarms.get('total', 0),
        'in_alarm': cw_alarms.get('in_alarm', 0),
        'ok': cw_alarms.get('ok', 0),
        'insufficient_data': cw_alarms.get('insufficient_data', 0),
    }
else:
    cw_alarms_list = cw_alarms if isinstance(cw_alarms, list) else []
    cw_summary = cw_data.get('summary', {})
```

### 2. CloudWatch Rows Function Field Name Mismatch
**Problem**: The function was using incorrect field names (`state`, `name`, `metric_name`, `threshold`) instead of AWS API field names (`StateValue`, `AlarmName`, `MetricName`, `Threshold`).

**Solution**:
- Updated `generate_cloudwatch_rows()` to support both field name formats
- Added type checking to skip non-dictionary items
- Used proper CSS badge classes for state styling

**Code Changes**:
```python
# Now supports both formats:
name = alarm.get('AlarmName', alarm.get('name', 'N/A'))
state = alarm.get('StateValue', alarm.get('state', 'UNKNOWN'))
metric = alarm.get('MetricName', alarm.get('metric_name', 'N/A'))
threshold = alarm.get('Threshold', alarm.get('threshold', 'N/A'))
```

### 3. Trusted Advisor Data Return Keys Mismatch
**Problem**: The `process_trusted_advisor_data()` function was returning incorrect keys that didn't match the template variables.

**Returned Keys**: `ta_cost_optimization`, `ta_security`, `ta_fault_tolerance`, etc.
**Expected Keys**: `ta_security_error`, `ta_security_warning`, `ta_fault_tolerance_error`, etc.

**Solution**:
- Updated the function to return the correct keys expected by the template
- Added `ta_error_rows` for the Trusted Advisor error table

## Testing Instructions

### On EC2:
```bash
# 1. Pull the latest code
cd /home/ec2-user/aws-zendesk-assistant
git pull origin main

# 2. Restart the WebSocket server
sudo pkill -f websocket_server.py
nohup python3 websocket_server.py > /tmp/websocket_server.log 2>&1 &

# 3. Check the logs
tail -f /tmp/websocket_server.log

# 4. Test with a report generation query
# Send a message to Zendesk app asking for a security report
```

### Expected Behavior:
- No more `AttributeError: 'str' object has no attribute 'get'` errors
- HTML report should generate successfully
- CloudWatch alarms section should display properly with correct styling
- Trusted Advisor section should show correct metrics

## Files Modified
- `websocket_server.py`: Fixed CloudWatch data handling and Trusted Advisor keys

## Commit
- Commit: `30aeb36`
- Message: "Fix CloudWatch and Trusted Advisor data structure handling in HTML report generation"
