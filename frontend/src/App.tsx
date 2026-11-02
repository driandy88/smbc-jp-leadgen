import { useEffect, useState } from "react";
import { api, session } from "./api";
import { Route, Shell } from "./components/Shell";
import { DesignFrame } from "./screens/DesignFrame";
import { Login } from "./screens/Login";
import { Scout } from "./screens/scout/Scout";

const routeFromHash = (): Route => {
  const h = window.location.hash.replace("#/", "");
  return h === "score" || h === "field" ? h : "scout";
};

export function App() {
  const [authed, setAuthed] = useState(!!session.token);
  const [initials, setInitials] = useState("··");
  const [route, setRoute] = useState<Route>(routeFromHash);
  const [dataChip, setDataChip] = useState("");

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash());
    const onLogout = () => setAuthed(false);
    const onMsg = (e: MessageEvent) => {
      if (e.origin !== window.location.origin || e.data?.type !== "hexline-nav") return;
      if (e.data.to === "login") logout();
      else nav(e.data.to);
    };
    window.addEventListener("hashchange", onHash);
    window.addEventListener("hexline-logout", onLogout);
    window.addEventListener("message", onMsg);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("hexline-logout", onLogout);
      window.removeEventListener("message", onMsg);
    };
  }, []);

  useEffect(() => {
    if (!authed) return;
    api<{ initials: string }>("/api/auth/me").then((m) => setInitials(m.initials)).catch(() => {});
    api<{ name: string }[]>("/api/versions").then((v) => v[0] && setDataChip((c) => c || v[0].name)).catch(() => {});
  }, [authed]);

  const nav = (r: Route) => {
    window.location.hash = `#/${r}`;
    setRoute(r);
  };
  const logout = () => {
    session.clear();
    setAuthed(false);
  };

  if (!authed) return <Login onLogin={(token, ini) => { session.set(token); setInitials(ini); setAuthed(true); nav("scout"); }} />;
  // Score and Field are the static design pages, which carry their own nav rail and header
  if (route !== "scout") return <DesignFrame page={route} />;
  return (
    <Shell route={route} onNav={nav} onLogout={logout} initials={initials} dataChip={dataChip}>
      <Scout onDataChip={setDataChip} />
    </Shell>
  );
}
