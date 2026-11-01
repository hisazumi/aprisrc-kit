export type PwaView = "app" | "console" | "lab";
export type ServiceMode = "student" | "carry" | "receptionist" | "greeting";

export function viewForPathname(pathname: string): PwaView {
  const section = pathname.split("/")[1];
  if (section === "console") return "console";
  if (section === "lab" || section === "playground") return "lab";
  return "app";
}

export function serviceModeForSearch(search: string): ServiceMode {
  const params = new URLSearchParams(search);
  const value = params.get("service") ?? params.get("sample");
  if (value === "student" || value === "my-service") return "student";
  if (value === "receptionist" || value === "greeting") return value;
  if (value === "carry" || value === "follow") return "carry";
  return "student";
}

export function viewUrl(view: PwaView, service: ServiceMode, search = ""): string {
  const params = new URLSearchParams(search);
  params.delete("sample");
  params.set("service", service === "student" ? "my-service" : service);
  const path = view === "app" ? "/service" : view === "lab" ? "/playground" : "/console";
  return `${path}?${params}`;
}
