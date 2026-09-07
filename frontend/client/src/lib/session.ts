import type { AnalysisSession, Profile, SearchSession } from "@/lib/types";
const read = <T>(key: string) => { try { const v = sessionStorage.getItem(key); return v ? JSON.parse(v) as T : null; } catch { return null; } };
const write = <T>(key: string, val: T) => sessionStorage.setItem(key, JSON.stringify(val));
export const loadProfile = () => read<Profile>("carrery:profile"); export const saveProfile = (v: Profile) => write("carrery:profile", v);
export const loadSearch = () => read<SearchSession>("carrery:search"); export const saveSearch = (v: SearchSession) => write("carrery:search", v);
export const loadAnalysis = () => read<AnalysisSession>("carrery:analysis"); export const saveAnalysis = (v: AnalysisSession) => write("carrery:analysis", v);
