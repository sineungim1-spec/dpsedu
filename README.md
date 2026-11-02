# DPS EDU — 동력전달장치 학습 플랫폼

## 3단계: 회원·관리자 화면 준비 버전

### 파일 구조
- `index.html`: 통합 홈페이지 및 화면 미리보기 진입
- `simulator.html`: 기존 동력전달장치 가상 조립 시뮬레이터
- `signup.html`: 이메일·이름·비밀번호 3개 항목 회원가입 입력 검증
- `login.html`: 이메일·비밀번호 2개 항목 로그인 UI 및 미리보기
- `mypage.html`: 프로필과 개인 실습 미리보기 기록
- `admin.html`: 회원·실습 활동·콘텐츠 관리 대시보드 UI
- `assets/auth.css`: 공통 반응형 스타일
- `assets/auth.js`: 인증/프로필/활동 데이터 어댑터
- `assets/simulator-bridge.js`: 시뮬레이터 활동 이벤트 연결
- `netlify.toml`: 정적 배포 설정

## 현재 단계에서 가능한 것
- 회원가입 폼의 이메일·이름·비밀번호 입력 검증 및 비밀번호 표시/숨김
- 로그인 UI와 실제 인증 미연결 안내
- 일반 회원/관리자 화면 미리보기 진입
- 마이페이지의 프로필 미리보기 및 실습 기록 확인
- 관리자 화면의 콘텐츠 추가·수정·선택 삭제, 실습 기록 검색·선택 삭제·CSV 다운로드
- 기존 시뮬레이터의 부품 드래그, 중심축 조정, 끼워맞춤, 마운팅, 검사, 기록 테이블, CSV 다운로드

## 중요한 보안/기능 제한
- 회원가입과 로그인은 실제로 수행되지 않습니다. 제출 버튼은 인증 서버 미연결 안내를 표시합니다.
- 비밀번호를 localStorage/sessionStorage/cookie에 저장하지 않습니다.
- 회원가입 입력 후 화면 미리보기를 위해 이름과 이메일만 세션에 보관할 수 있습니다.
- 미리보기는 인증이나 권한 부여가 아닙니다. 관리자 화면 미리보기는 누구나 접근 가능한 UI 확인용이며 실제 관리자 권한을 의미하지 않습니다.
- 실제 회원 목록은 서버 연결 전까지 0명으로 표시합니다. 고정 계정/기본 비밀번호는 없습니다.
- 실습 기록과 콘텐츠 변경은 현재 브라우저의 미리보기 데이터입니다. 다른 기기와 동기화되지 않습니다.
- 기존 시뮬레이터의 기록 테이블과 CSV 출력은 유지됩니다. Excel/PDF 내보내기는 기존 구현에 없으므로 새로 추가하지 않았습니다.

## 4단계 Supabase 연결 계약
`assets/auth.js`의 공개 함수 이름을 유지하고 내부를 Supabase JS 클라이언트 기반 구현으로 교체합니다.
- `signUpUser({displayName,email,password})`: Supabase Auth signUp 호출 후 `profiles`에 이름 저장
- `signInUser({email,password})`: Supabase Auth signInWithPassword
- `signOutUser()`: Supabase Auth signOut
- `getCurrentUser()`, `getUserRole()`, `getUserProfile()`
- `updateUserProfile({displayName})`
- `getUsers()`, `getActivityRecords()`, `saveActivityRecord(record)`
- `getDashboardData()`

### 권장 데이터 구조
- `profiles`: `id uuid primary key references auth.users(id)`, `display_name text`, `role text not null default 'user'`, `created_at timestamptz`
- `activity_records`: `id uuid primary key`, `user_id uuid references auth.users(id)`, `fit_type text`, `bearing_error numeric`, `shaft_error numeric`, `cover_error numeric`, `mount_status text`, `result text`, `created_at timestamptz`
- `simulator_contents`: `id uuid primary key`, `title text`, `subject text`, `status text`, `created_at timestamptz`, `updated_at timestamptz`

RLS 필수 정책: 회원은 본인 프로필/실습 기록만 읽고 수정, 관리자는 서버에서 검증된 role claim 또는 안전한 권한 테이블을 통해 허용된 작업만 수행합니다. 회원가입 요청의 metadata로 role을 받지 말고 DB 기본값은 항상 `user`로 설정합니다. 최초 관리자 지정은 소유자가 SQL Editor/보안된 관리 절차로 직접 수행합니다. service_role 키는 브라우저나 공개 저장소에 절대 넣지 않습니다.

## 5단계 Google OAuth
Supabase Auth의 Google provider와 Google Cloud OAuth client/redirect URI를 설정한 뒤 Google 로그인 버튼을 활성화합니다. OAuth client secret은 Supabase 대시보드에만 보관합니다.

## 배포
Netlify는 저장소의 `main` 브랜치와 publish 디렉터리 `.`를 사용합니다. 커밋 후 자동 배포가 시작되며, Deploys 탭에서 배포 완료 여부를 확인하세요.
