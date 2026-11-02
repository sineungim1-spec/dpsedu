# DPS EDU 3단계 회원·관리자 체험 기능

## 파일 구조
- `index.html`: 통합 홈
- `login.html`: 로그인 및 체험 계정 진입
- `signup.html`: 회원가입 입력 검증 체험
- `mypage.html`: 프로필 및 내 실습 기록
- `admin.html`: 관리자 대시보드(체험용)
- `simulator.html`: 기존 동력전달장치 시뮬레이터 보존본
- `assets/auth.css`: 공통 반응형 스타일
- `assets/auth.js`: 인증 데이터 어댑터(현재 demo 모드)
- `assets/simulator-bridge.js`: 기존 실습 저장 이벤트 연결

## 체험 계정
- 일반 사용자: `student@dpsedu.local`
- 관리자: `admin@dpsedu.local`
- 로그인 화면에서 바로 체험 버튼을 눌러도 됩니다.
- 비밀번호는 인증되지 않으며 저장·전송하지 않습니다.

## 실행
`index.html`을 브라우저에서 엽니다. GitHub Pages/Netlify에 배포할 때는 저장소 파일 구조를 그대로 사용합니다.

## 기존 기능 보존
원래 `index.html`의 시뮬레이터 본문과 조작 코드를 `simulator.html`로 옮겼습니다. 실험 기록 시 계정 어댑터로 이벤트를 전달하는 연결 코드만 추가했습니다. 원래 실습 화면의 기록 테이블과 CSV 다운로드는 계속 브라우저 안에서 동작합니다.

## 중요: 체험 모드의 한계
- 실제 회원가입, 비밀번호 인증, 비밀번호 재설정 메일은 동작하지 않습니다.
- 체험 프로필은 세션 저장소, 활동/콘텐츠 데모 데이터는 브라우저 로컬 저장소에 저장됩니다. 비밀번호는 저장하지 않습니다.
- 관리자 역할은 클라이언트 코드에서만 구분되므로 개발자 도구로 우회할 수 있습니다. 실제 서비스의 권한 보호로 사용하면 안 됩니다.
- 실습 기록은 현재 브라우저의 로컬 데이터이며 여러 기기 간 동기화되지 않습니다.

## 4단계 Supabase 연결 계획
`assets/auth.js`의 공개 함수 인터페이스를 유지하고 내부 구현을 Supabase 호출로 교체합니다.
- Auth: `signUpUser`, `signInUser`, `signOutUser`, `getCurrentUser`
- 프로필: `getUserRole`, `getUserProfile`, `updateProfile`
- 활동: `getActivityRecords`, `saveActivityRecord`, `updateActivityRecord`, `deleteActivityRecord`
- 대시보드: `getDashboardData`

권장 테이블:
- `profiles`: `id`(auth.users FK), `display_name`, `role`, `created_at`
- `activity_records`: `id`, `user_id`, `fit_type`, `bearing_error`, `shaft_error`, `cover_error`, `mount_status`, `result`, `created_at`
- `simulator_contents`: `id`, `title`, `subject`, `status`, `created_at`, `updated_at`

## 5단계 Google 로그인
Supabase Auth의 Google provider 설정, Google Cloud OAuth client 등록, 승인된 redirect URI 등록 후 `signInWithOAuth({provider:'google'})`를 `signInUser` 주변 UI에 연결합니다.
