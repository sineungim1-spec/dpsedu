# DPS EDU — 동력전달장치 학습 플랫폼

## 주요 화면
- `index.html`: 기존 학습 플랫폼 홈
- `login.html`: 아이디·비밀번호 로그인
- `signup.html`: 아이디·이름·비밀번호 회원가입
- `mypage.html`: 프로필, 비밀번호, 개인 실습 기록
- `admin.html`: 회원·활동 데이터·콘텐츠·관리자 설정
- `simulator.html`: 기존 동력전달장치 가상 조립 시뮬레이터
- `assets/auth.js`: 인증·계정·데이터 저장 어댑터
- `assets/simulator-bridge.js`: 시뮬레이터 기록과 로그인 계정 연결

## 최초 관리자
- 아이디: `admin`
- 초기 비밀번호: `1234`
- 최초 실행 시 브라우저에 관리자 계정이 생성됩니다. 관리자 설정에서 즉시 비밀번호를 변경하세요.
- 일반 회원가입으로 관리자 역할을 만들 수 없습니다.

## 회원가입 및 저장
회원가입은 아이디(영문·숫자·._- 3~24자), 이름, 비밀번호(8자 이상)만 입력합니다. 비밀번호는 사용자별 salt와 PBKDF2(SHA-256, 150,000회)로 파생한 값만 브라우저 저장소에 보관합니다. 비밀번호 원문은 저장하지 않습니다. 계정과 기록은 같은 브라우저의 localStorage, 로그인 상태는 sessionStorage에 저장됩니다.

## 실행
정적 호스팅(Netlify 등) 또는 로컬 웹 서버에서 HTTPS/localhost로 실행하세요. Web Crypto API는 보안 컨텍스트가 필요합니다.

## 보안상 중요
현재 구현은 단일 브라우저 교육·시연용입니다. HTML/JavaScript와 브라우저 저장소는 사용자가 수정할 수 있으므로 공개 서비스의 인증·관리자 권한 보호 수단으로 사용하면 안 됩니다. 다른 기기와 데이터가 공유되지 않습니다. 운영 전에는 Supabase Auth 등 서버 인증과 데이터베이스 RLS로 교체하고, 관리자 역할과 회원·기록 CRUD를 서버에서 검증해야 합니다. 브라우저 저장소의 PBKDF2 해시는 서버 인증을 대체하지 않습니다.

## 데이터 인터페이스
`assets/auth.js`의 `window.DpsAuth`는 화면 코드와 저장 계층을 분리합니다. 주요 메서드: `signUp`, `signIn`, `signOut`, `getCurrentUser`, `getUserRole`, `getUsers`, `updateUser`, `deleteUsers`, `getRecords`, `saveRecord`, `updateRecord`, `deleteRecord`, `getDashboardData`, `changePassword`. 다음 단계에서는 이 어댑터 내부 구현을 서버 API로 교체하면 됩니다.

## 기존 기능 보존
기존 `simulator.html`은 별도 파일로 보존했습니다. 부품 드래그, 중심축 조정, 끼워맞춤, 마운팅, 조립 검사, 실습 테이블과 CSV 기능을 유지합니다.
