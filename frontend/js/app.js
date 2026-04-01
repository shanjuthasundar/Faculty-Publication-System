const currentPage = document.body.dataset.page;

async function init() {
  if (currentPage === "login") {
    const module = await import("./pages/login-page.js");
    await module.initLoginPage();
    return;
  }

  if (currentPage === "dashboard") {
    const module = await import("./pages/dashboard-page.js");
    await module.initDashboardPage();
    return;
  }

  if (currentPage === "new-publication") {
    const module = await import("./pages/publication-form-page.js");
    await module.initPublicationFormPage();
  }
}

init().catch((error) => {
  alert(error.message || "Unexpected app error");
});
