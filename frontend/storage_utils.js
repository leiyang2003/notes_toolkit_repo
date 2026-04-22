(function (global) {
  function readStoredProject() {
    try {
      return localStorage.getItem("notes_dashboard_last_project") || "";
    } catch (_err) {
      return "";
    }
  }

  function writeStoredProject(projectName) {
    try {
      if (projectName) {
        localStorage.setItem("notes_dashboard_last_project", projectName);
      } else {
        localStorage.removeItem("notes_dashboard_last_project");
      }
    } catch (_err) {
      // Storage access can fail in strict browser modes; ignore.
    }
  }

  global.NotesDashboardStorage = {
    readStoredProject: readStoredProject,
    writeStoredProject: writeStoredProject,
  };
})(window);
