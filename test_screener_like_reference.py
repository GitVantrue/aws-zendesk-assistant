#!/usr/bin/env python3
"""
Reference 코드와 동일한 방식으로 Service Screener 테스트
slack_bot_screener_main.py의 로직을 따라 실행
"""

import os
import sys
import subprocess
import json
from datetime import datetime

def run_screener_like_reference(account_id=None):
    """
    Reference 코드(slack_bot_screener_main.py)와 동일한 방식으로 Service Screener 실행
    
    Reference 코드는 main.py를 호출하므로, 우리도 main.py를 호출해야 함
    """
    
    print("\n" + "="*70)
    print("🚀 Reference 코드 방식으로 Service Screener 테스트")
    print("="*70 + "\n")
    
    # 1. AWS 자격증명 확인
    print("1️⃣ AWS 자격증명 확인...")
    result = subprocess.run(
        ['aws', 'sts', 'get-caller-identity', '--query', 'Account', '--output', 'text'],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    if result.returncode != 0:
        print(f"❌ AWS 자격증명 오류: {result.stderr}")
        return False
    
    current_account = result.stdout.strip()
    print(f"✅ 현재 계정: {current_account}\n")
    
    # 2. Service Screener 경로 확인
    print("2️⃣ Service Screener 경로 확인...")
    screener_main = '/root/service-screener-v2/main.py'
    
    if not os.path.exists(screener_main):
        print(f"❌ {screener_main} 파일을 찾을 수 없습니다")
        return False
    
    print(f"✅ {screener_main} 존재\n")
    
    # 3. Reference 코드 방식: main.py 호출
    print("3️⃣ Reference 코드 방식으로 main.py 호출...")
    print("   (slack_bot_screener_main.py와 동일한 방식)\n")
    
    # Reference 코드의 명령어 구성
    # main.py --regions ap-northeast-2 --services all --crossAccounts /path/to/crossAccounts.json
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # crossAccounts.json 생성
    temp_json_path = f'/tmp/crossAccounts_test_{timestamp}.json'
    cross_accounts_config = {
        "general": {
            "IncludeThisAccount": True,
            "Regions": ["ap-northeast-2", "us-east-1"]
        }
    }
    
    with open(temp_json_path, 'w') as f:
        json.dump(cross_accounts_config, f, indent=2)
    
    print(f"📝 crossAccounts.json 생성: {temp_json_path}\n")
    
    # main.py 호출 (Reference 코드 방식)
    cmd = [
        'python3',
        screener_main,
        '--regions', 'ap-northeast-2,us-east-1',
        '--services', 'all',
        '--crossAccounts', temp_json_path
    ]
    
    print(f"📋 실행 명령어:")
    print(f"   {' '.join(cmd)}\n")
    
    print(f"⏱️ 약 2-5분 소요될 수 있습니다...\n")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd='/root/service-screener-v2'
        )
        
        print(f"✅ 반환 코드: {result.returncode}\n")
        
        # stdout 출력
        if result.stdout:
            print("📤 stdout (마지막 1000자):")
            print("-" * 70)
            print(result.stdout[-1000:])
            print("-" * 70 + "\n")
        
        # stderr 출력
        if result.stderr:
            print("📥 stderr (마지막 1000자):")
            print("-" * 70)
            print(result.stderr[-1000:])
            print("-" * 70 + "\n")
        
        # 결과 디렉터리 확인
        print("🔍 결과 디렉터리 확인:")
        result_dir = f'/root/service-screener-v2/adminlte/aws/{current_account}'
        
        if os.path.exists(result_dir):
            print(f"✅ 결과 디렉터리 발견: {result_dir}")
            
            # 파일 목록
            files = []
            for root, dirs, filenames in os.walk(result_dir):
                for filename in filenames:
                    files.append(os.path.join(root, filename))
            
            print(f"   파일 개수: {len(files)}")
            
            # index.html 확인
            index_html = os.path.join(result_dir, 'index.html')
            if os.path.exists(index_html):
                print(f"✅ index.html 발견: {index_html}")
            else:
                print(f"❌ index.html을 찾을 수 없음")
            
            return result.returncode == 0
        else:
            print(f"❌ 결과 디렉터리 없음: {result_dir}")
            print("   → 권한 부족이거나 스캔이 실패했을 수 있습니다")
            return False
        
    except subprocess.TimeoutExpired:
        print("❌ Service Screener 타임아웃 (10분)")
        return False
    except Exception as e:
        print(f"❌ Service Screener 실행 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_screener_like_reference()
    
    print("\n" + "="*70)
    if success:
        print("✅ Service Screener 테스트 성공!")
    else:
        print("❌ Service Screener 테스트 실패")
    print("="*70 + "\n")
    
    sys.exit(0 if success else 1)
