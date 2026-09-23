import { Page } from '@playwright/test';

export const moduleTitle = 'Distributed Systems and Cloud Application Development';
export async function mockWorkspace(page: Page) {
  const state = { role: 'student', locked: true };
  const today = new Date().toLocaleDateString('en-CA');
  const catalog: Record<string, unknown[]> = {
    modules: [{ id: 1, code: 'IT6001', title: moduleTitle, credits: 20 }],
    teachers: [{ id: 1, name: 'Alexandria Sharma - Computing Department', employee_code: 'T001' }],
    'class-types': [{ id: 1, name: 'Practical workshop' }],
    blocks: [{ id: 1, name: 'Computing Building' }], rooms: [{ id: 1, block_id: 1, name: 'Laboratory 301', capacity: 40 }],
    'time-slots': [{ id: 1, start_time: '09:00:00', end_time: '10:00:00' }],
    sections: [{ id: 1, name: 'Section A', batch_id: 1 }],
    programs: [{ id: 1, name: 'BSc Information Technology' }],
    batches: [{ id: 1, name: 'BSc Information Technology 2026-2029', program_id: 1, start_date: '2026-09-01', end_date: '2029-08-31', levels: [1,2,3].map(n => ({ id: n, level_number: n, intake_code: `NP0${n}`, intake_name: `Level ${n}` })) }],
    intakes: [{ id: 1, name: 'Autumn 2026', code: 'NP01', batch_id: 1 }],
  };
  const occurrence = { routine_id: 1, date: today, start_time: '09:00:00', end_time: '10:00:00', module_id: 1, teacher_id: 1, class_type_id: 1, room: 'Computing Building / Laboratory 301', original_room: 'Computing Building / Laboratory 301', section_names: ['Section A'], cancelled: false };
  const routines = [{ id: 1, day_of_week: 0, module_id: 1, teacher_id: 1, class_type_id: 1, room_id: 1, block_id: 1, time_slot_id: 1, intake_id: 1, section_ids: [1], section_names: ['Section A'] }];
  const account = () => ({ id: 2, name: 'An unusually long student account name', email: 'student.with.a.long.email@example.com', role: 'student', is_active: true, is_locked: state.locked, failed_login_attempts: state.locked ? 5 : 0, college_id: 1 });
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname.replace('/api/v1/', '');
    let data: unknown = [];
    if (path === 'auth/me') data = { ...account(), id: 1, role: state.role, college_name: 'Techspire College', active_college_id: state.role === 'super_admin' ? null : 1 };
    else if (path.endsWith('/unlock')) { state.locked = false; data = account(); }
    else if (path === 'users') data = [account()];
    else if (path === 'platform/users') data = { items: [account()], total: 1, page: 1, page_size: 25 };
    else if (path === 'platform/colleges') data = [{ id: 1, name: 'Techspire College', slug: 'techspire', is_active: true }];
    else if (path === 'platform/overview') data = { colleges: 1, students: 140, teachers: 12, active_sessions: 3 };
    else if (path === 'academic/catalog') data = catalog;
    else if (path.includes('occurrences')) data = [occurrence];
    else if (path.endsWith('routines/me') || path.endsWith('teachers/me/routines')) data = routines;
    else if (path === 'academic/room-availability') data = { date: today, day_of_week: 1, blocks: [{id:1,name:'Computing Building',rooms:[{id:1,name:'Laboratory 301',room_type:'Lab',capacity:40,slots:[{time_slot_id:1,start_time:'09:00:00',end_time:'10:00:00',status:'occupied',class_label:moduleTitle,section_names:['Section A']}]}]}] };
    else if (path === 'analytics/my-attendance') data = { student_id: 2, date_from: today, date_to: today, present: 1, absent: 0, total: 1, overall_percentage: 100, attendance_threshold_percent: 75, minimum_observations: 4, subjects: [{subject_id:1,subject_name:moduleTitle,present:1,absent:0,total:1,percentage:100}], days:[{date:today,weekday:'Wednesday',present:1,absent:0,total:1,percentage:100,records:[{session_id:1,date:today,weekday:'Wednesday',subject_id:1,subject_name:moduleTitle,subject_code:'IT6001',class_type_id:1,class_type_name:'Practical workshop',status:'present',check_in_time:new Date().toISOString()}]}] };
    else if (path === 'sessions/1/qr') data = { token:'test-qr-value',classroom_code:'123456',expires_at:new Date(Date.now()+20000).toISOString(),rotation_seconds:20,self_checkin_window_minutes:15,self_checkin_closes_at:new Date(Date.now()+600000).toISOString(),module_title:moduleTitle,section_names:['Section A'],room:'Laboratory 301',start_time:'09:00:00',end_time:'10:00:00',geofence_radius_meters:150,teacher_location_accuracy_meters:12,challenge_id:1,teacher_ip_status:'campus' };
    else if (path === 'sessions/1/summary') data = [ {attendance_id:1,student_id:2,student_name:account().name,roll_number:'NP001-2026-0001',status:'present',check_in_time:new Date().toISOString(),distance_meters:15,allowed_radius_meters:150,location_accuracy_meters:8,ip_status:'campus'}, {attendance_id:null,student_id:3,student_name:'Sam Rai',roll_number:'NP001-2026-0002',status:'pending_verification',check_in_time:null,distance_meters:180,allowed_radius_meters:150,location_accuracy_meters:12,ip_status:'outside'} ];
    else if (path === 'sessions/1/check-in-exceptions') data = [{id:1,student_name:'Sam Rai',roll_number:'NP001-2026-0002',section_name:'Section A',reason:'outside_geofence',distance_meters:180,allowed_radius_meters:150,accuracy_meters:12,created_at:new Date().toISOString(),status:'pending'}];
    else if (path === 'academic/semester-resources/semesters') data = [{id:1,intake_name:'Autumn 2026',batch_name:'BSc Information Technology 2026-2029',semester_number:1,attempt_number:1,start_date:'2026-09-01',end_date:'2027-02-28',calendar:{id:1,filename:'Academic Calendar Autumn Semester 2026.pdf',size_bytes:102400,uploaded_at:new Date().toISOString()}}];
    else if (path.endsWith('/page')) { const kind=path.split('/').at(-2)!;data={items:catalog[kind]||[],total:(catalog[kind]||[]).length,page:1,page_size:20}; }
    else if (path === 'academic/cohort-semesters') data = [1,2].map(n=>({id:n,batch_level_id:1,level_number:1,intake_id:1,intake_code:'NP01',batch_id:1,batch_name:'BSc Information Technology 2026-2029',semester_number:n,start_date:n===1?'2026-09-01':'2027-03-01',end_date:n===1?'2027-02-28':'2027-08-31',status:'active',calendar_uploaded:true,label:`Semester ${n}`}));
    else if (path === 'academic/promotions') data = [{id:1,intake_id:1,batch_id:1,from_cohort_semester_id:1,to_cohort_semester_id:2,effective_date:'2027-03-01',promoted_students:1,held_students:1}];
    else if (path === 'academic/promotions/preview' || path === 'academic/section-placements/preview') data = {total_students:2,promote_count:1,assign_count:1,hold_count:1,errors:[],preview_signature:'test-only',students:[{id:2,name:account().name,roll_number:'NP001-0001',source_section_id:1,target_section_id:1,action:'promote',reason:null},{id:3,name:'Sam Rai',roll_number:'NP001-0002',source_section_id:1,target_section_id:null,action:'hold',reason:'Manual hold'}]};
    else if (path === 'academic/promotions/1/students') data = [{id:3,promotion_run_item_id:1,name:'Sam Rai',roll_number:'NP001-0002',source_section_id:1,target_section_id:null,action:'hold',reason:'Manual hold'}];
    else if (path === 'teacher/attendance') data = [{...occurrence,session_id:1,module_code:'IT6001',module_title:moduleTitle,session_status:'active',students:[{attendance_id:1,student_id:2,student_name:account().name,roll_number:'NP001-2026-0001',status:'present',ip_status:'campus'}]}];
    else if (path === 'cases') data = [{id:1,student_id:2,trigger_type:'low_attendance_follow_up',priority:'high',assigned_to:'Coordinator'}];
    else if (path.startsWith('academic/')) data = catalog[path.split('/').at(-1)!] || [];
    else if (path === 'auth/forgot-password') data = {message:'If an account exists for that email, password reset instructions have been sent.'};
    else if (path.startsWith('auth/reset-password')) data = {message:'Password reset complete'};
    await route.fulfill({ json: data });
  });
  return state;
}
