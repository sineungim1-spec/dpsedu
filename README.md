# DPS EDU — 동력전달장치 학습 플랫폼

## 주요 화면
- `index.html`: 학습 플랫폼 홈
- `login.html`: Supabase 이메일·비밀번호 로그인
- `signup.html`: 이메일·이름·비밀번호 회원가입
- `mypage.html`: 프로필, 비밀번호, 개인 실습 기록
- `admin.html`: 회원·활동 데이터·콘텐츠·서비스 설정 관리
- `simulator.html`: 기존 동력전달장치 가상 조립 시뮬레이터
- `assets/auth.js`: Supabase Auth 및 데이터 접근 어댑터
- `assets/supabase-config.js`: 공개 Project URL 및 Publishable key
- `assets/simulator-bridge.js`: 시뮬레이터 실습 이벤트 저장 연결

## Supabase 설정
브라우저에는 Supabase Project URL과 Publishable key만 사용합니다. Secret/service_role key는 절대 클라이언트 파일에 넣지 않습니다. Supabase SQL Editor에서 기존 스키마와 RLS 정책 및 `handle_new_user()` 호환성 수정 SQL을 적용해야 합니다.

회원가입 시 Auth 사용자 메타데이터의 `display_name`과 `name`을 전달합니다. DB 트리거가 `profiles` 행을 생성하며 기본 역할은 `user`입니다. 비밀번호는 Supabase Auth가 관리하고 애플리케이션 테이블에 별도 저장하지 않습니다.

## 관리자 최초 설정
1. Supabase Authentication > Users에서 관리자로 사용할 이메일 계정을 먼저 회원가입합니다.
2. 해당 계정의 UUID를 확인합니다.
3. SQL Editor에서 아래와 같이 해당 계정만 관리자로 승격합니다.

```sql
update public.profiles
set role = 'admin'
where id = '관리자-auth-사용자-UUID';
```

이 SQL은 신뢰할 수 있는 프로젝트 소유자만 실행해야 합니다. 웹 화면에는 역할 승격 기능이 없습니다. 일반 가입자는 트리거에서 항상 `user`로 생성됩니다.

## 데이터 구조
- `profiles`: Auth 사용자와 연결된 프로필
- `activity_records`: 실습 기록 및 원본 `record_data`
- `simulator_contents`: 관리자 콘텐츠
- `app_settings`: 관리자 서비스 설정

실습 저장은 `activity_records.user_id`에 현재 Auth 사용자 UUID를 기록합니다. 조회·수정·삭제 범위는 Supabase RLS 정책이 최종 결정합니다. 관리자 회원 삭제 기능은 서버의 `admin_delete_user(target_user_id)` RPC가 필요합니다.

## 배포
정적 HTML을 현재 Cloudflare Pages/Workers 정적 호스팅 방식으로 배포하면 됩니다. 별도 빌드 단계는 없습니다. 변경 파일을 GitHub main에 반영한 뒤 Cloudflare의 기존 Git 연동 배포 또는 현재 배포 방식으로 다시 배포하세요.

## 점검 사항
- Supabase Auth의 Email provider가 활성화되어 있어야 합니다.
- 이메일 인증을 사용하는 경우 가입 후 인증 메일 링크를 눌러야 로그인할 수 있습니다.
- Auth URL Configuration의 Site URL 및 Redirect URLs에 실제 배포 도메인과 로그인/가입 경로를 허용해야 합니다.
- 테이블의 RLS 정책과 권한 부여가 앞서 적용한 SQL과 일치해야 합니다.
- 기존 localStorage에 있던 체험 계정·실습 기록은 자동으로 Supabase로 이전되지 않습니다.
- 이 저장소의 브라우저 코드는 실제 Supabase 프로젝트에 접속하지만, 이 작업 과정에서 Supabase SQL 실행, Cloudflare 배포, 실제 브라우저 통합 테스트는 수행하지 않았습니다.
