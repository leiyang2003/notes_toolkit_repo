import DashboardApp from "../../../components/dashboard-app";

export default function ProjectPage({ params }) {
  return <DashboardApp initialProjectName={decodeURIComponent(params.project)} />;
}
