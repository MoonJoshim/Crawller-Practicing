#!/usr/bin/env python3
"""
간단한 Flask API 서버 - 강의명 검색으로 에브리타임 크롤링
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import urllib.parse
import time
import os
from dotenv import load_dotenv
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import json

# 환경변수 로드
load_dotenv()

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 한글 JSON 응답을 위해
CORS(app)  # CORS 허용

def setup_driver():
    """Chrome 웹드라이버 설정"""
    chrome_options = Options()
    # chrome_options.add_argument("--headless")  # reCAPTCHA 때문에 헤드리스 모드 비활성화
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # macOS에서 Chrome 실행 파일 경로 명시
    chrome_options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    
    driver_path = ChromeDriverManager().install()
    if "THIRD_PARTY_NOTICES.chromedriver" in driver_path:
        driver_path = driver_path.replace("THIRD_PARTY_NOTICES.chromedriver", "chromedriver")
    
    service = Service(driver_path)
    return webdriver.Chrome(service=service, options=chrome_options)

def login_to_everytime(driver):
    """에브리타임 로그인"""
    try:
        print("🔐 에브리타임 로그인 중...")
        driver.get("https://everytime.kr/login")
        time.sleep(3)
        
        # ID 입력 (페이지 구조 변경에 따라 수정)
        try:
            id_input = driver.find_element(By.NAME, "userid")
        except:
            id_input = driver.find_element(By.NAME, "id")
        id_input.send_keys(os.getenv("EVERYTIME_ID"))
        
        # 비밀번호 입력
        pw_input = driver.find_element(By.NAME, "password")
        pw_input.send_keys(os.getenv("EVERYTIME_PASSWORD"))
        
        # 로그인 버튼 클릭
        login_btn = driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]')
        login_btn.click()
        
        print("🤖 reCAPTCHA가 있을 수 있습니다. 수동으로 해결해주세요...")
        print("⏰ 30초 대기 중... (reCAPTCHA 해결 후 자동 진행)")
        
        # reCAPTCHA 해결을 위해 더 긴 대기 시간
        for i in range(30):
            time.sleep(1)
            current_url = driver.current_url
            
            # 로그인 성공 확인 (URL 변경 또는 특정 요소 존재)
            if "login" not in current_url.lower() or "everytime.kr/" in current_url:
                print("로그인 성공!")
                return True
                
            # Alert 처리
            try:
                alert = driver.switch_to.alert
                alert_text = alert.text
                alert.accept()
                print(f"로그인 실패 - Alert: {alert_text}")
                return False
            except:
                pass
        
        print("⏰ 시간 초과 - 로그인 확인 불가")
        return False
            
    except Exception as e:
        print(f"로그인 오류: {str(e)}")
        return False

def search_lecture(driver, keyword):
    """강의 검색"""
    try:
        print(f"🔍 '{keyword}' 검색 중...")
        
        # 강의실 페이지로 이동
        driver.get("https://everytime.kr/lecture")
        time.sleep(3)
        
        # 과목명 라디오 버튼 선택 (기본값이지만 명시적으로 선택)
        try:
            subject_radio = driver.find_element(By.CSS_SELECTOR, 'input[value="subject"]')
            if not subject_radio.is_selected():
                subject_radio.click()
                time.sleep(1)
        except:
            print("⚠️ 과목명 라디오 버튼을 찾을 수 없음")
        
        # 검색창 찾기 (여러 선택자 시도)
        search_input = None
        selectors = [
            'input[placeholder*="과목"]',
            'input[name="keyword"]',
            'input[type="text"]',
            '#keyword'
        ]
        
        for selector in selectors:
            try:
                search_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"검색창 발견: {selector}")
                break
            except:
                continue
                
        if not search_input:
            print("검색창을 찾을 수 없음")
            return []
        
        # 검색어 입력
        search_input.clear()
        search_input.send_keys(keyword)
        
        # 검색 버튼 클릭 또는 엔터
        try:
            search_button = driver.find_element(By.CSS_SELECTOR, 'input[type="submit"], button[type="submit"]')
            search_button.click()
        except:
            search_input.submit()
            
        time.sleep(5)
        
        # 검색 결과 수집
        lectures = []
        try:
            print("🔍 검색 결과 페이지 분석 중...")
            
            # 페이지 소스 일부 확인 (디버깅용)
            page_source = driver.page_source
            print(f"📄 페이지 길이: {len(page_source)} 문자")
            
            # 여러 선택자로 강의 목록 찾기 시도
            selectors = [
                '.item',           # 기본 아이템
                '.lecture',        # 강의 클래스
                'tr',             # 테이블 행
                '.list tr',       # 리스트 내 테이블 행
                '[class*="item"]', # item이 포함된 클래스
                '.course',        # 코스 클래스
                'li'              # 리스트 아이템
            ]
            
            lecture_items = []
            for selector in selectors:
                try:
                    items = driver.find_elements(By.CSS_SELECTOR, selector)
                    if items:
                        print(f"✅ 선택자 '{selector}'로 {len(items)}개 요소 발견")
                        lecture_items = items[:10]  # 최대 10개만
                        break
                except:
                    continue
            
            if not lecture_items:
                print("❌ 강의 목록 요소를 찾을 수 없음")
                # 페이지 소스 일부 출력 (디버깅)
                print("📝 페이지 소스 일부:")
                print(page_source[:1000])
                return []
            
            print(f"📋 {len(lecture_items)}개 요소에서 강의 정보 추출 시도")
            
            for i, item in enumerate(lecture_items):
                try:
                    print(f"📝 요소 {i+1} 분석 중...")
                    
                    # 강의명 추출 (여러 선택자 시도)
                    subject = ""
                    subject_selectors = ['.name', '.subject', '.title', 'td:first-child', '.course-name']
                    for sel in subject_selectors:
                        try:
                            subject_elem = item.find_element(By.CSS_SELECTOR, sel)
                            subject = subject_elem.text.strip()
                            if subject:
                                print(f"   ✅ 강의명: '{subject}' (선택자: {sel})")
                                break
                        except:
                            continue
                    
                    if not subject:
                        print(f"   ❌ 강의명을 찾을 수 없음 - 요소 텍스트: '{item.text[:50]}...'")
                        continue
                    
                    # 교수명 추출 (여러 선택자 시도)
                    professor = "정보 없음"
                    professor_selectors = ['.professor', '.teacher', '.instructor', 'td:nth-child(2)', '.prof']
                    for sel in professor_selectors:
                        try:
                            professor_elem = item.find_element(By.CSS_SELECTOR, sel)
                            professor = professor_elem.text.strip()
                            if professor:
                                print(f"   ✅ 교수명: '{professor}' (선택자: {sel})")
                                break
                        except:
                            continue
                    
                    # 평점 추출 (여러 선택자 시도)
                    rating = 0.0
                    rating_selectors = ['.rating', '.score', '.rate', '.grade']
                    for sel in rating_selectors:
                        try:
                            rating_elem = item.find_element(By.CSS_SELECTOR, sel)
                            rating_text = rating_elem.text.strip()
                            if rating_text:
                                rating = float(rating_text)
                                print(f"   ✅ 평점: {rating} (선택자: {sel})")
                                break
                        except:
                            continue
                    
                    lectures.append({
                        'subject': subject,
                        'professor': professor,
                        'rating': rating,
                        'reviewCount': 0,  # 임시값
                        'reviews': [],
                        'details': {
                            'attendance': '정보 없음',
                            'exam': '정보 없음',
                            'assignment': '정보 없음',
                            'teamProject': '정보 없음'
                        }
                    })
                    
                except Exception as e:
                    print(f"강의 정보 추출 오류: {e}")
                    continue
                    
        except Exception as e:
            print(f"검색 결과 처리 오류: {e}")
        
        print(f"{len(lectures)}개 강의 발견")
        return lectures
        
    except Exception as e:
        print(f"검색 오류: {str(e)}")
        return []

@app.route('/api/search', methods=['GET'])
def api_search():
    """강의 검색 API"""
    keyword = request.args.get('keyword', '').strip()
    
    # 한글 인코딩 문제 해결
    original_keyword = keyword
    try:
        # 1. URL 디코딩 시도
        if '%' in keyword:
            keyword = urllib.parse.unquote(keyword)
            print(f"📝 URL 디코딩: '{original_keyword}' → '{keyword}'")
        
        # 2. UTF-8 바이트 문제 해결
        if isinstance(keyword, bytes):
            keyword = keyword.decode('utf-8')
            print(f"📝 바이트 디코딩: bytes → '{keyword}'")
            
        # 3. 잘못된 UTF-8 해석 수정 (Latin-1로 해석된 UTF-8을 다시 디코딩)
        if len(keyword.encode('utf-8')) != len(keyword):
            try:
                # Latin-1로 인코딩한 후 UTF-8로 디코딩
                keyword = keyword.encode('latin-1').decode('utf-8')
                print(f"📝 UTF-8 재해석: '{original_keyword}' → '{keyword}'")
            except:
                pass
                
    except Exception as e:
        print(f"⚠️ 키워드 디코딩 오류: {e}")
    
    print(f"🔍 최종 검색 키워드: '{keyword}' (길이: {len(keyword)}) [원본길이: {len(original_keyword)}]")
    
    if not keyword:
        return jsonify({'error': '검색어를 입력해주세요'}), 400
    
    # 모의 데이터 (다양한 과목 포함)
    mock_data = {
        "실전코딩": [{
            "subject": "실전코딩 1",
            "professor": "최재영",
            "rating": 4.50,
            "reviewCount": 32,
            "reviews": [
                {"rating": 5.0, "comment": "무난 그 자체. P/F라 부담도 없고 과제도 하라는 데로만 하면 됨.", "semester": "23년 1학기"},
                {"rating": 1.0, "comment": "학점따기에는 괜춘\n근데 이걸로 무언가를 실제로 배웠냐? x\n진짜 말 그대로 찍먹임\n찍먹아니고 그냥 찍임 \n코드 복붙 따라쓰기 수업끝\n\n개인적으로는 학점 필요한거 아니면 안듣는거 추천.", "semester": "24년 2학기"},
                {"rating": 4.5, "comment": "P/F 과목이라 부담없이 들을 수 있음. 기초적인 프로그래밍 개념을 배울 수 있어서 좋음.", "semester": "23년 2학기"},
                {"rating": 4.0, "comment": "교수님이 친절하시고 설명을 잘해주심. 과제는 시간 투자하면 충분히 할 수 있는 수준.", "semester": "22년 2학기"},
                {"rating": 5.0, "comment": "코딩 처음 배우는 사람에게 추천. 차근차근 설명해주시고 실습도 많아서 도움됨.", "semester": "22년 1학기"},
                {"rating": 3.0, "comment": "내용이 너무 기초적임. 이미 프로그래밍 경험이 있다면 지루할 수 있음.", "semester": "23년 1학기"},
                {"rating": 4.0, "comment": "과제량이 적당하고 시험이 없어서 좋음. P/F라서 부담도 없음.", "semester": "24년 1학기"},
                {"rating": 5.0, "comment": "프로그래밍 입문자에게 최고. 교수님도 좋으시고 수업도 알찬 편.", "semester": "21년 2학기"},
                {"rating": 4.5, "comment": "실습 위주 수업이라 이해하기 쉬움. 과제도 적당한 수준이고 교수님도 좋으심.", "semester": "22년 1학기"},
                {"rating": 2.0, "comment": "너무 쉬워서 배우는게 없음. 이미 코딩 경험이 있다면 비추천.", "semester": "23년 2학기"},
                {"rating": 4.0, "comment": "기초부터 차근차근 가르쳐주셔서 좋음. P/F라 부담없이 들을 수 있어요.", "semester": "24년 1학기"},
                {"rating": 5.0, "comment": "최고의 입문 수업! 프로그래밍 처음 하는 사람들에게 강추합니다.", "semester": "21년 1학기"}
            ],
            "details": {
                "attendance": "직접호명, 전자출결",
                "exam": "없음",
                "assignment": "보통 (66%)",
                "teamProject": "없음 (88%)"
            }
        }],
        "데이터베이스": [{
            "subject": "데이터베이스",
            "professor": "김영수",
            "rating": 3.8,
            "reviewCount": 29,
            "reviews": [
                {"rating": 4.0, "comment": "난이도가 높지만 체계적으로 가르쳐주십니다. SQL 실습이 많아서 도움됨.", "semester": "24년 1학기"},
                {"rating": 3.5, "comment": "이론이 많고 어려워요. 하지만 실무에 도움되는 내용들이 많음.", "semester": "23년 2학기"},
                {"rating": 4.5, "comment": "교수님이 친절하시고 실습 예제가 좋음. 과제는 좀 많지만 배우는게 많아요.", "semester": "23년 1학기"},
                {"rating": 2.5, "comment": "너무 어려워요... 중간고사 망했습니다. 예습 필수인 것 같아요.", "semester": "24년 1학기"},
                {"rating": 4.0, "comment": "DB 설계부터 SQL까지 전반적으로 잘 가르쳐주심. 과제 부담은 있음.", "semester": "22년 2학기"},
                {"rating": 3.0, "comment": "내용은 좋은데 진도가 너무 빨라요. 복습 필수.", "semester": "23년 1학기"}
            ],
            "details": {
                "attendance": "직접호명",
                "exam": "중간, 기말",
                "assignment": "많음",
                "teamProject": "있음"
            }
        }],
        "자료구조": [{
            "subject": "자료구조",
            "professor": "박민수",
            "rating": 4.2,
            "reviewCount": 45,
            "reviews": [
                {"rating": 5.0, "comment": "알고리즘 공부하기 전에 꼭 들어야 할 과목. 교수님 설명 최고!", "semester": "24년 1학기"},
                {"rating": 4.0, "comment": "과제가 많지만 실력 향상에 도움됨. 코딩테스트 준비에도 좋아요.", "semester": "23년 2학기"},
                {"rating": 3.5, "comment": "개념은 중요한데 구현이 어려워요. 복습 많이 해야 함.", "semester": "23년 1학기"},
                {"rating": 4.5, "comment": "트리, 그래프 등 중요한 개념들을 잘 설명해주심. 추천!", "semester": "22년 2학기"},
                {"rating": 2.0, "comment": "너무 어려워서 따라가기 힘듦. 기초가 부족하면 고생함.", "semester": "24년 1학기"},
                {"rating": 4.0, "comment": "실습 위주라 좋음. 과제는 시간 투자하면 할 수 있는 수준.", "semester": "23년 2학기"}
            ],
            "details": {
                "attendance": "전자출결",
                "exam": "중간, 기말",
                "assignment": "많음",
                "teamProject": "없음"
            }
        }],
        "운영체제": [{
            "subject": "운영체제",
            "professor": "이정민",
            "rating": 3.9,
            "reviewCount": 38,
            "reviews": [
                {"rating": 4.0, "comment": "개념이 어렵지만 중요한 내용. 교수님이 차근차근 설명해주심.", "semester": "24년 1학기"},
                {"rating": 3.0, "comment": "이론 위주라 지루할 수 있음. 하지만 꼭 알아야 할 내용들.", "semester": "23년 2학기"},
                {"rating": 4.5, "comment": "프로세스, 스레드 개념을 정말 잘 가르쳐주심. 추천합니다.", "semester": "23년 1학기"},
                {"rating": 2.5, "comment": "너무 어려워요. 암기할 것도 많고 이해하기 힘듦.", "semester": "24년 1학기"},
                {"rating": 4.0, "comment": "시스템 프로그래밍에 관심 있다면 필수 과목. 유익함.", "semester": "22년 2학기"}
            ],
            "details": {
                "attendance": "직접호명",
                "exam": "중간, 기말",
                "assignment": "보통",
                "teamProject": "없음"
            }
        }],
        "웹프로그래밍": [{
            "subject": "웹프로그래밍",
            "professor": "최현우",
            "rating": 4.6,
            "reviewCount": 52,
            "reviews": [
                {"rating": 5.0, "comment": "실습 위주라 재밌음! HTML, CSS, JS부터 React까지 배울 수 있어요.", "semester": "24년 1학기"},
                {"rating": 4.5, "comment": "프론트엔드 개발에 관심 있다면 강추. 포트폴리오도 만들 수 있음.", "semester": "23년 2학기"},
                {"rating": 4.0, "comment": "과제가 좀 많지만 실무에 도움되는 내용들. 교수님도 친절하심.", "semester": "23년 1학기"},
                {"rating": 5.0, "comment": "최고의 실습 수업! 웹 개발의 전반적인 흐름을 배울 수 있어요.", "semester": "22년 2학기"},
                {"rating": 3.5, "comment": "진도가 빨라서 따라가기 힘들 수 있음. 예습 필수.", "semester": "24년 1학기"},
                {"rating": 4.5, "comment": "프로젝트 중심 수업이라 좋음. 팀워크도 기를 수 있어요.", "semester": "23년 2학기"}
            ],
            "details": {
                "attendance": "전자출결",
                "exam": "없음",
                "assignment": "많음",
                "teamProject": "있음"
            }
        }],
        "알고리즘": [{
            "subject": "알고리즘",
            "professor": "강태호",
            "rating": 3.7,
            "reviewCount": 33,
            "reviews": [
                {"rating": 4.0, "comment": "어렵지만 코딩테스트에 정말 도움됨. 꼭 들어야 할 과목.", "semester": "24년 1학기"},
                {"rating": 2.5, "comment": "너무 어려워요... 수학적 사고력이 필요함. 포기하고 싶었음.", "semester": "23년 2학기"},
                {"rating": 4.5, "comment": "동적계획법, 그래프 알고리즘 등 중요한 내용 많음. 추천!", "semester": "23년 1학기"},
                {"rating": 3.0, "comment": "이론은 좋은데 구현이 어려워요. 연습 많이 해야 함.", "semester": "22년 2학기"},
                {"rating": 4.0, "comment": "취업 준비에 필수. 어렵지만 끝까지 해볼 만한 가치 있음.", "semester": "24년 1학기"}
            ],
            "details": {
                "attendance": "전자출결",
                "exam": "중간, 기말",
                "assignment": "많음",
                "teamProject": "없음"
            }
        }],
        "소프트웨어공학": [{
            "subject": "소프트웨어공학",
            "professor": "김소프트",
            "rating": 4.1,
            "reviewCount": 25,
            "reviews": [
                {"rating": 4.5, "comment": "개발 프로세스부터 테스팅까지 전반적으로 배울 수 있어요. 실무에 도움됨.", "semester": "24년 1학기"},
                {"rating": 3.5, "comment": "이론 위주지만 중요한 내용들. 팀 프로젝트가 좀 힘들어요.", "semester": "23년 2학기"},
                {"rating": 4.0, "comment": "UML, 설계 패턴 등 유익한 내용 많음. 추천합니다.", "semester": "23년 1학기"},
                {"rating": 2.5, "comment": "너무 이론적이고 지루함. 실습이 더 있었으면 좋겠어요.", "semester": "24년 1학기"},
                {"rating": 4.5, "comment": "소프트웨어 개발자 꿈꾸는 사람에게 필수 과목!", "semester": "22년 2학기"}
            ],
            "details": {
                "attendance": "전자출결",
                "exam": "중간, 기말",
                "assignment": "보통",
                "teamProject": "있음"
            }
        }],
        "네트워크": [{
            "subject": "컴퓨터네트워크",
            "professor": "박네트워크",
            "rating": 3.6,
            "reviewCount": 31,
            "reviews": [
                {"rating": 4.0, "comment": "TCP/IP부터 라우팅까지 체계적으로 배울 수 있음. 어렵지만 유익해요.", "semester": "24년 1학기"},
                {"rating": 3.0, "comment": "개념이 어렵고 암기할 것이 많아요. 복습 필수.", "semester": "23년 2학기"},
                {"rating": 4.5, "comment": "네트워크 관리자 꿈꾸는 사람에게 추천. 실습도 있어서 좋음.", "semester": "23년 1학기"},
                {"rating": 2.0, "comment": "너무 어려워서 포기하고 싶었음. 기초 지식 필요.", "semester": "24년 1학기"},
                {"rating": 3.5, "comment": "이론은 딱딱하지만 실무에서 꼭 필요한 내용들.", "semester": "22년 2학기"}
            ],
            "details": {
                "attendance": "직접호명",
                "exam": "중간, 기말",
                "assignment": "보통",
                "teamProject": "없음"
            }
        }],
        "머신러닝": [{
            "subject": "머신러닝",
            "professor": "이에이아이",
            "rating": 4.3,
            "reviewCount": 42,
            "reviews": [
                {"rating": 5.0, "comment": "AI 시대에 꼭 필요한 과목! Python 실습도 많고 재밌어요.", "semester": "24년 1학기"},
                {"rating": 4.0, "comment": "수학적 배경 지식이 필요하지만 흥미로운 내용들. 추천!", "semester": "23년 2학기"},
                {"rating": 3.5, "comment": "개념은 좋은데 구현이 어려워요. 과제 부담 있음.", "semester": "23년 1학기"},
                {"rating": 4.5, "comment": "딥러닝까지 다뤄서 좋음. 취업에도 도움될 것 같아요.", "semester": "22년 2학기"},
                {"rating": 2.5, "comment": "수학을 못하면 따라가기 힘듦. 선형대수 미리 공부하세요.", "semester": "24년 1학기"}
            ],
            "details": {
                "attendance": "전자출결",
                "exam": "중간, 기말",
                "assignment": "많음",
                "teamProject": "있음"
            }
        }],
        "모바일프로그래밍": [{
            "subject": "모바일프로그래밍",
            "professor": "최모바일",
            "rating": 4.4,
            "reviewCount": 38,
            "reviews": [
                {"rating": 5.0, "comment": "안드로이드 앱 개발을 처음부터 끝까지! 포트폴리오도 만들 수 있어요.", "semester": "24년 1학기"},
                {"rating": 4.0, "comment": "Java 기초가 있으면 좋음. 실습 위주라 재밌어요.", "semester": "23년 2학기"},
                {"rating": 4.5, "comment": "앱스토어에 출시까지 해볼 수 있어서 좋음. 추천!", "semester": "23년 1학기"},
                {"rating": 3.0, "comment": "과제가 많고 디버깅이 힘들어요. 인내심 필요.", "semester": "22년 2학기"},
                {"rating": 4.5, "comment": "모바일 개발자 꿈꾸는 사람에게 최고의 과목!", "semester": "24년 1학기"}
            ],
            "details": {
                "attendance": "전자출결",
                "exam": "없음",
                "assignment": "많음",
                "teamProject": "있음"
            }
        }],
        "게임프로그래밍": [{
            "subject": "게임프로그래밍",
            "professor": "강게임",
            "rating": 4.7,
            "reviewCount": 29,
            "reviews": [
                {"rating": 5.0, "comment": "Unity로 게임 만드는 과목! 정말 재밌고 실습 위주라 좋아요.", "semester": "24년 1학기"},
                {"rating": 4.5, "comment": "C# 기초부터 게임 엔진까지 배울 수 있음. 강추!", "semester": "23년 2학기"},
                {"rating": 4.0, "comment": "과제는 많지만 재밌어서 시간 가는 줄 모름. 추천해요.", "semester": "23년 1학기"},
                {"rating": 5.0, "comment": "게임 개발자 꿈꾸는 사람에게 최고! 포트폴리오도 만들 수 있어요.", "semester": "22년 2학기"},
                {"rating": 3.5, "comment": "재밌지만 디버깅이 어려워요. 인내심과 창의력 필요.", "semester": "24년 1학기"}
            ],
            "details": {
                "attendance": "전자출결",
                "exam": "없음",
                "assignment": "많음",
                "teamProject": "있음"
            }
        }],
        "보안": [{
            "subject": "정보보안",
            "professor": "박보안",
            "rating": 3.9,
            "reviewCount": 27,
            "reviews": [
                {"rating": 4.0, "comment": "해킹부터 암호학까지 폭넓게 배울 수 있어요. 흥미로운 과목.", "semester": "24년 1학기"},
                {"rating": 3.5, "comment": "이론이 많고 어려워요. 하지만 중요한 내용들.", "semester": "23년 2학기"},
                {"rating": 4.5, "comment": "실습으로 해킹 기법도 배우고 재밌어요. 추천!", "semester": "23년 1학기"},
                {"rating": 2.5, "comment": "너무 어렵고 암기할 것이 많아요. 수학 기초 필요.", "semester": "22년 2학기"},
                {"rating": 4.0, "comment": "보안 전문가 되고 싶다면 필수 과목. 유익함.", "semester": "24년 1학기"}
            ],
            "details": {
                "attendance": "직접호명",
                "exam": "중간, 기말",
                "assignment": "보통",
                "teamProject": "없음"
            }
        }]
    }
    
    # 검색 결과 찾기 (부분 일치 지원)
    results = []
    keyword_lower = keyword.lower()
    
    for key, lectures in mock_data.items():
        # 키워드가 과목명에 포함되어 있는지 확인
        if keyword_lower in key.lower():
            results.extend(lectures)
        else:
            # 각 강의의 과목명과 교수명에서도 검색
            for lecture in lectures:
                if keyword_lower in lecture['subject'].lower() or keyword_lower in lecture['professor'].lower():
                    results.append(lecture)
    
    # 중복 제거
    seen = set()
    unique_results = []
    for result in results:
        identifier = f"{result['subject']}_{result['professor']}"
        if identifier not in seen:
            seen.add(identifier)
            unique_results.append(result)
    
    # 실제 크롤링 시도 (모의 데이터에 없는 경우)
    if not unique_results:
        print(f"📡 모의 데이터에 없음. 실제 크롤링 시도: {keyword}")
        try:
            driver = setup_driver()
            if login_to_everytime(driver):
                crawled_results = search_lecture(driver, keyword)
                unique_results.extend(crawled_results)
                print(f"실제 크롤링 완료: {len(crawled_results)}개 강의 발견")
            else:
                print("로그인 실패")
            driver.quit()
        except Exception as e:
            print(f"실제 크롤링 오류: {str(e)}")
            unique_results = []
    
    return jsonify({
        'keyword': keyword,
        'results': unique_results,
        'count': len(unique_results)
    })

@app.route('/api/crawl', methods=['GET'])
def api_crawl():
    """실제 크롤링 API (시간이 오래 걸림)"""
    keyword = request.args.get('keyword', '').strip()
    
    if not keyword:
        return jsonify({'error': '검색어를 입력해주세요'}), 400
    
    driver = None
    try:
        # 웹드라이버 설정
        driver = setup_driver()
        
        # 로그인
        if not login_to_everytime(driver):
            return jsonify({'error': '로그인 실패'}), 500
        
        # 검색
        results = search_lecture(driver, keyword)
        
        return jsonify({
            'keyword': keyword,
            'results': results,
            'count': len(results),
            'crawled': True
        })
        
    except Exception as e:
        return jsonify({'error': f'크롤링 오류: {str(e)}'}), 500
    
    finally:
        if driver:
            driver.quit()

@app.route('/')
def index():
    """메인 페이지"""
    return '''
    <h1>에브리타임 강의평 크롤링 API</h1>
    <p>사용법:</p>
    <ul>
        <li><code>/api/search?keyword=실전코딩</code> - 빠른 검색 (모의 데이터)</li>
        <li><code>/api/crawl?keyword=실전코딩</code> - 실제 크롤링 (느림)</li>
    </ul>
    '''

if __name__ == '__main__':
    print("🚀 에브리타임 강의평 크롤링 API 서버 시작")
    print("📍 http://localhost:5002")
    print("🔧 실제 크롤링 기능 활성화됨")
    app.run(debug=True, host='0.0.0.0', port=5002)
