#!/usr/bin/env python3
"""
Service Screener 디버깅 테스트 스크립트
스캔이 실제로 작동하는지 단계별로 확인
"""

import os
import sys
import subprocess
import json
from datetime import datetime

def print_section(title):
    """섹션 제목 출력"""
    print(f"\n{'='*60}")
    print(f"🔍 {title}")
    print(f"{'='*60}\n")

def test_screener_path():
    """Service Screener 경로 확인"""
    print_section("1. Service Screener 경로 확인")
    
    screener_path = '/root/service-screener-v2/Screener.py'
    print(f"경로: {screener_path}")
    print(f"존재: {os.path.exists(screener_path)}")
    
    if os.path.exists(screener_path):
        print(f"파일 크기: {os.path.getsize(screener_path)} bytes")
        print(f"실행 가능: {os.access(screener_path, os.X_OK)}")
    
    return os.path.exists(screener_path)

def test_python_import():
    """Python에서 Screener 임포트 가능한지 확인"""
    print_section("2. Python 임포트 테스트")
    
    try:
        sys.path.insert(0, '/root/service-screener-v2')
        import Screener
        print("✅ Screener 모듈 임포트 성공")
        return True
    except Exception as e:
        print(f"❌ Screener 모듈 임포트 실패: {e}")
        return False

def test_aws_credentials():
    """AWS 자격증명 확인"""
    print_section("3. AWS 자격증명 확인")
    
    env_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN']
    
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            masked = value[:20] + '...' if len(value) > 20 else value
            print(f"✅ {var}: {masked}")
        else:
            print(f"❌ {var}: 설정되지 않음")
    
    # AWS CLI 테스트
    print("\n🔐 AWS CLI 계정 검증:")
    try:
        result = subprocess.run(
            ['aws', 'sts', 'get-caller-identity', '--query', 'Account', '--output', 'text'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            account_id = result.stdout.strip()
            print(f"✅ 계정 ID: {account_id}")
            return account_id
        else:
            print(f"❌ AWS CLI 실패: {result.stderr}")
            return None
    except Exception as e:
        print(f"❌ AWS CLI 오류: {e}")
        return None

def test_screener_direct_run(account_id):
    """Service Screener 직접 실행 테스트"""
    print_section("4. Service Screener 직접 실행 테스트")
    
    if not account_id:
        print("❌ 계정 ID가 없어서 테스트 불가")
        return False
    
    screener_path = '/root/service-screener-v2/Screener.py'
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # crossAccounts.json 생성
    temp_json_path = f'/tmp/crossAccounts_test_{timestamp}.json'
    cross_accounts_config = {
        "general": {
            "IncludeThisAccount": True,
            "Regions": ["ap-northeast-2"]  # 한 리전만 테스트
        }
    }
    
    with open(temp_json_path, 'w') as f:
        json.dump(cross_accounts_config, f, indent=2)
    
    print(f"crossAccounts.json 생성: {temp_json_path}")
    
    # Service Screener 실행
    cmd = [
        'python3',
        screener_path,
        '--crossAccounts', temp_json_path
    ]
    
    print(f"\n실행 명령어: {' '.join(cmd)}")
    print(f"작업 디렉터리: /root/service-screener-v2")
    print(f"타임아웃: 120초 (테스트용 짧은 시간)\n")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd='/root/service-screener-v2'
        )
        
        print(f"반환 코드: {result.returncode}")
        
        if result.stdout:
            print(f"\n📤 stdout (처음 500자):\n{result.stdout[:500]}")
        
        if result.stderr:
            print(f"\n📥 stderr (처음 500자):\n{result.stderr[:500]}")
        
        # 결과 디렉터리 확인
        print(f"\n🔍 결과 디렉터리 확인:")
        possible_dirs = [
            f'/root/service-screener-v2/aws/{account_id}',
            f'/root/service-screener-v2/adminlte/aws/{account_id}'
        ]
        
        for dir_path in possible_dirs:
            exists = os.path.exists(dir_path)
            print(f"  {dir_path}: {'✅ 존재' if exists else '❌ 없음'}")
            
            if exists:
                files = os.listdir(dir_path)
                print(f"    파일 개수: {len(files)}")
                print(f"    파일 목록: {files[:5]}...")
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("❌ Service Screener 타임아웃 (120초)")
        return False
    except Exception as e:
        print(f"❌ Service Screener 실행 오류: {e}")
        return False

def test_result_directory_structure():
    """결과 디렉터리 구조 확인"""
    print_section("5. 결과 디렉터리 구조 확인")
    
    screener_base = '/root/service-screener-v2'
    
    # 주요 디렉터리 확인
    dirs_to_check = [
        'aws',
        'adminlte',
        'adminlte/aws',
        'adminlte/aws/res'
    ]
    
    for dir_name in dirs_to_check:
        dir_path = os.path.join(screener_base, dir_name)
        exists = os.path.exists(dir_path)
        print(f"{dir_name}: {'✅' if exists else '❌'}")
        
        if exists and os.path.isdir(dir_path):
            try:
                items = os.listdir(dir_path)
                print(f"  → {len(items)} 항목")
            except Exception as e:
                print(f"  → 읽기 실패: {e}")

def test_crossaccounts_json():
    """crossAccounts.json 형식 테스트"""
    print_section("6. crossAccounts.json 형식 테스트")
    
    test_configs = [
        {
            "name": "기본 설정",
            "config": {
                "general": {
                    "IncludeThisAccount": True,
                    "Regions": ["ap-northeast-2"]
                }
            }
        },
        {
            "name": "다중 리전",
            "config": {
                "general": {
                    "IncludeThisAccount": True,
                    "Regions": ["ap-northeast-2", "us-east-1"]
                }
            }
        }
    ]
    
    for test in test_configs:
        print(f"\n{test['name']}:")
        print(json.dumps(test['config'], indent=2))

def main():
    """메인 테스트 함수"""
    print("\n" + "="*60)
    print("🚀 Service Screener 디버깅 테스트 시작")
    print("="*60)
    
    results = {}
    
    # 1. 경로 확인
    results['path'] = test_screener_path()
    
    # 2. Python 임포트
    results['import'] = test_python_import()
    
    # 3. AWS 자격증명
    account_id = test_aws_credentials()
    results['credentials'] = account_id is not None
    
    # 4. 결과 디렉터리 구조
    test_result_directory_structure()
    
    # 5. crossAccounts.json 형식
    test_crossaccounts_json()
    
    # 6. Service Screener 직접 실행 (계정 ID가 있을 때만)
    if account_id:
        results['screener_run'] = test_screener_direct_run(account_id)
    else:
        print_section("4. Service Screener 직접 실행 테스트")
        print("❌ 계정 ID가 없어서 테스트 불가")
        results['screener_run'] = False
    
    # 최종 결과
    print_section("📊 테스트 결과 요약")
    
    for test_name, result in results.items():
        status = "✅ 성공" if result else "❌ 실패"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ 모든 테스트 통과!")
    else:
        print("❌ 일부 테스트 실패 - 위의 결과를 확인하세요")
    print("="*60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
