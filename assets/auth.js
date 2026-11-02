/* DPS EDU Supabase Auth + database adapter.
   Only the Supabase publishable key is used in this browser client.
   Access control is enforced by Supabase RLS and server-side functions. */
(function () {
  'use strict';

  const client = window.supabase.createClient(
    window.DPS_SUPABASE_URL,
    window.DPS_SUPABASE_PUBLISHABLE_KEY,
    {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true
      }
    }
  );

  let session = null;
  let profile = null;
  let readyPromise = null;
  let authListenerStarted = false;

  function fail(error) {
    if (error) throw new Error(error.message || '요청을 처리하지 못했습니다.');
  }

  function publicUser(p) {
    if (!p) return null;
    return {
      id: p.id,
      username: p.username || '',
      name: p.display_name || '',
      displayName: p.display_name || '',
      email: p.email || session?.user?.email || '',
      role: p.role || 'user',
      createdAt: p.created_at || null
    };
  }

  async function loadProfile(authSession) {
    session = authSession || null;
    profile = null;
    if (!session?.user) return null;

    const { data, error } = await client
      .from('profiles')
      .select('id, username, display_name, role, created_at')
      .eq('id', session.user.id)
      .maybeSingle();

    fail(error);
    if (!data) {
      throw new Error('회원 프로필이 아직 생성되지 않았습니다. Supabase의 handle_new_user 트리거와 SQL 수정 여부를 확인해 주세요.');
    }
    profile = { ...data, email: session.user.email || '' };
    return publicUser(profile);
  }

  async function ready() {
    if (readyPromise) return readyPromise;
    readyPromise = (async () => {
      const { data, error } = await client.auth.getSession();
      fail(error);
      await loadProfile(data.session);

      if (!authListenerStarted) {
        authListenerStarted = true;
        client.auth.onAuthStateChange((_event, nextSession) => {
          // Avoid awaiting Supabase calls inside the auth callback.
          Promise.resolve().then(() => loadProfile(nextSession)).catch(console.error);
        });
      }
      return publicUser(profile);
    })().catch(error => {
      readyPromise = null;
      throw error;
    });
    return readyPromise;
  }

  async function signUp({ email, name, password } = {}) {
    await ready();
    email = String(email || '').trim().toLowerCase();
    name = String(name || '').trim();
    password = String(password || '');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('올바른 이메일 주소를 입력해 주세요.');
    if (!name) throw new Error('이름을 입력해 주세요.');
    if (password.length < 8) throw new Error('비밀번호는 8자 이상이어야 합니다.');

    const { data, error } = await client.auth.signUp({
      email,
      password,
      options: {
        data: {
          display_name: name,
          name
        }
      }
    });
    fail(error);
    if (data.session) await loadProfile(data.session);
    return {
      id: data.user?.id || null,
      email,
      name,
      needsEmailConfirmation: !data.session
    };
  }

  async function signIn({ email, password } = {}) {
    await ready();
    email = String(email || '').trim().toLowerCase();
    const { data, error } = await client.auth.signInWithPassword({ email, password: String(password || '') });
    fail(error);
    await loadProfile(data.session);
    return publicUser(profile);
  }

  async function signOut() {
    const { error } = await client.auth.signOut();
    fail(error);
    session = null;
    profile = null;
    return true;
  }

  async function requireLogin() {
    await ready();
    if (!session?.user || !profile) {
      const next = location.pathname.split('/').pop() || 'index.html';
      location.replace('login.html?next=' + encodeURIComponent(next));
      return null;
    }
    return publicUser(profile);
  }

  async function requireAdmin() {
    const user = await requireLogin();
    if (!user) return null;
    if (user.role !== 'admin') {
      location.replace('index.html');
      return null;
    }
    return user;
  }

  async function updateProfile({ name } = {}) {
    const user = await requireLogin();
    if (!user) throw new Error('로그인이 필요합니다.');
    name = String(name || '').trim();
    if (!name) throw new Error('이름을 입력해 주세요.');

    const { error } = await client.from('profiles')
      .update({ display_name: name })
      .eq('id', user.id);
    fail(error);

    const { error: metaError } = await client.auth.updateUser({ data: { display_name: name, name } });
    fail(metaError);
    await loadProfile(session);
    return publicUser(profile);
  }

  async function changePassword({ currentPassword, newPassword } = {}) {
    const user = await requireLogin();
    if (!user) throw new Error('로그인이 필요합니다.');
    if (String(newPassword || '').length < 8) throw new Error('새 비밀번호는 8자 이상이어야 합니다.');

    const { error: verifyError } = await client.auth.signInWithPassword({
      email: user.email,
      password: String(currentPassword || '')
    });
    fail(verifyError);

    const { error } = await client.auth.updateUser({ password: String(newPassword) });
    fail(error);
    return true;
  }

  async function getUsers() {
    const { data, error } = await client.from('profiles')
      .select('id, username, display_name, role, created_at')
      .order('created_at', { ascending: false });
    fail(error);
    return (data || []).map(p => ({
      id: p.id, username: p.username || '', name: p.display_name || '',
      displayName: p.display_name || '', role: p.role || 'user', createdAt: p.created_at
    }));
  }

  function mapRecord(row, usersById = {}) {
    const raw = row.record_data && typeof row.record_data === 'object' ? row.record_data : {};
    const person = usersById[row.user_id] || {};
    return {
      ...raw,
      id: row.id,
      userId: row.user_id,
      username: person.username || '',
      displayName: person.display_name || '',
      fit: row.fit,
      bearingError: row.bearing_error,
      shaftError: row.shaft_error,
      coverError: row.cover_error,
      mountStatus: row.mount_status,
      result: row.result,
      createdAt: row.created_at
    };
  }

  async function getRecords() {
    const { data, error } = await client.from('activity_records')
      .select('id, user_id, fit, bearing_error, shaft_error, cover_error, mount_status, result, record_data, created_at')
      .order('created_at', { ascending: false });
    fail(error);

    const ids = [...new Set((data || []).map(r => r.user_id).filter(Boolean))];
    let usersById = {};
    if (ids.length) {
      const { data: people, error: peopleError } = await client.from('profiles')
        .select('id, username, display_name').in('id', ids);
      fail(peopleError);
      usersById = Object.fromEntries((people || []).map(p => [p.id, p]));
    }
    return (data || []).map(r => mapRecord(r, usersById));
  }

  async function saveRecord(record = {}) {
    const user = await requireLogin();
    if (!user) return null;
    const payload = {
      user_id: user.id,
      fit: record.fit ?? null,
      bearing_error: Number(record.bearingError ?? 0),
      shaft_error: Number(record.shaftError ?? 0),
      cover_error: Number(record.coverError ?? 0),
      mount_status: record.mountStatus ?? null,
      result: record.result ?? null,
      record_data: record
    };
    const { data, error } = await client.from('activity_records')
      .insert(payload)
      .select('id, user_id, fit, bearing_error, shaft_error, cover_error, mount_status, result, record_data, created_at')
      .single();
    fail(error);
    return mapRecord(data, { [user.id]: { username: user.username, display_name: user.name } });
  }

  async function updateRecord(id, patch = {}) {
    const dbPatch = {};
    if ('fit' in patch) dbPatch.fit = patch.fit;
    if ('bearingError' in patch) dbPatch.bearing_error = patch.bearingError;
    if ('shaftError' in patch) dbPatch.shaft_error = patch.shaftError;
    if ('coverError' in patch) dbPatch.cover_error = patch.coverError;
    if ('mountStatus' in patch) dbPatch.mount_status = patch.mountStatus;
    if ('result' in patch) dbPatch.result = patch.result;
    if ('record_data' in patch) dbPatch.record_data = patch.record_data;
    const { data, error } = await client.from('activity_records').update(dbPatch)
      .eq('id', id)
      .select('id, user_id, fit, bearing_error, shaft_error, cover_error, mount_status, result, record_data, created_at')
      .maybeSingle();
    fail(error);
    return data ? mapRecord(data) : null;
  }

  async function deleteRecord(id) {
    const { error } = await client.from('activity_records').delete().eq('id', id);
    fail(error);
    return true;
  }

  async function deleteRecords(ids = []) {
    if (!ids.length) return true;
    const { error } = await client.from('activity_records').delete().in('id', ids);
    fail(error);
    return true;
  }

  function mapContent(c) {
    return {
      ...c,
      url: c.content_url || 'simulator.html',
      visible: c.is_visible !== false
    };
  }

  async function getContents() {
    const { data, error } = await client.from('simulator_contents')
      .select('id, title, subject, objective, description, content_url, sort_order, is_visible, created_by, created_at')
      .order('sort_order', { ascending: true });
    fail(error);
    return (data || []).map(mapContent);
  }

  async function saveContent(content = {}) {
    const user = await requireAdmin();
    if (!user) throw new Error('관리자 권한이 필요합니다.');
    const payload = {
      title: String(content.title || '').trim(),
      subject: content.subject || null,
      objective: content.objective || null,
      description: content.description || null,
      content_url: content.url || content.content_url || 'simulator.html',
      is_visible: content.visible !== false,
      created_by: user.id
    };
    if (content.id) payload.id = content.id;
    const { data, error } = await client.from('simulator_contents')
      .upsert(payload)
      .select('id, title, subject, objective, description, content_url, sort_order, is_visible, created_by, created_at')
      .single();
    fail(error);
    return mapContent(data);
  }

  async function deleteContents(ids = []) {
    if (!ids.length) return true;
    const { error } = await client.from('simulator_contents').delete().in('id', ids);
    fail(error);
    return true;
  }

  async function deleteUsers(ids = []) {
    const user = await requireAdmin();
    if (!user) throw new Error('관리자 권한이 필요합니다.');
    if (ids.includes(user.id)) throw new Error('현재 로그인한 관리자 계정은 삭제할 수 없습니다.');
    for (const id of ids) {
      const { error } = await client.rpc('admin_delete_user', { target_user_id: id });
      fail(error);
    }
    return ids.length;
  }

  async function updateUser(id, patch = {}) {
    const user = await requireAdmin();
    if (!user) throw new Error('관리자 권한이 필요합니다.');
    if (patch.role && patch.role !== 'user') throw new Error('관리자 권한은 이 화면에서 부여할 수 없습니다.');
    const update = {};
    if (patch.name) update.display_name = String(patch.name).trim();
    const { data, error } = await client.from('profiles').update(update)
      .eq('id', id)
      .select('id, username, display_name, role, created_at')
      .single();
    fail(error);
    return { id: data.id, username: data.username, name: data.display_name, role: data.role, createdAt: data.created_at };
  }

  async function getDashboardData() {
    const user = await requireAdmin();
    if (!user) throw new Error('관리자 권한이 필요합니다.');
    const [users, records, contents] = await Promise.all([getUsers(), getRecords(), getContents()]);
    return {
      userCount: users.length,
      activityCount: records.length,
      contentCount: contents.length,
      users, records, contents
    };
  }

  async function getSettings() {
    const { data, error } = await client.from('app_settings')
      .select('setting_key, setting_value');
    fail(error);
    const settings = { programName: 'DPS EDU', homePage: 'index.html' };
    (data || []).forEach(row => { settings[row.setting_key] = row.setting_value; });
    return settings;
  }

  async function updateSettings(patch = {}) {
    const user = await requireAdmin();
    if (!user) throw new Error('관리자 권한이 필요합니다.');
    const rows = Object.entries(patch).map(([setting_key, setting_value]) => ({
      setting_key, setting_value, updated_by: user.id
    }));
    if (rows.length) {
      const { error } = await client.from('app_settings').upsert(rows, { onConflict: 'setting_key' });
      fail(error);
    }
    return getSettings();
  }

  document.addEventListener('DOMContentLoaded', async () => {
    try {
      await ready();
      const user = publicUser(profile);
      document.querySelectorAll('[data-user-label]').forEach(el => {
        el.textContent = user ? (user.name + ' · ' + user.email) : '';
      });
      document.querySelectorAll('[data-logout], #dpsNavLogout').forEach(el => {
        el.addEventListener('click', async () => {
          try { await signOut(); location.href = 'login.html'; }
          catch (error) { alert(error.message); }
        });
      });
      const state = document.getElementById('dpsNavState');
      if (state) state.textContent = user ? (user.name + ' 로그인 중') : '로그인 필요';
    } catch (error) {
      console.error('DPS EDU Supabase 초기화 오류:', error);
    }
  });

  window.DpsAuth = {
    ready,
    signUp, signIn, signOut,
    getCurrentUser: () => publicUser(profile),
    getUserRole: () => profile?.role || 'guest',
    getUserProfile: async () => { await ready(); return publicUser(profile); },
    requireLogin, requireAdmin,
    changePassword, updateProfile,
    getUsers, updateUser, deleteUsers,
    getRecords, saveRecord, updateRecord, deleteRecord, deleteRecords,
    getContents, saveContent, deleteContents,
    getDashboardData, getSettings, updateSettings,
    saveActivityRecord: saveRecord,
    getActivityRecords: getRecords,
    deleteActivityRecord: deleteRecord
  };

  ready().catch(error => console.error('DPS EDU Supabase 초기화 오류:', error));
})();