import { expect, test } from "@playwright/test";

test("client can edit structured report source and regenerate package", async ({ page }) => {
  const sessionId = "stub-structured-editor";

  await page.goto("/v4/chat");
  await page.evaluate((id) => {
    window.sessionStorage.setItem(
      `v4:${id}`,
      JSON.stringify({
        session_id: id,
        raw_question: "Проверить редактирование отчета",
        research_prompt: null,
        source_reports: [],
        analysis: null,
        followup_reports: [],
        status: "synthesized",
        created_at: new Date().toISOString(),
        total_cost_rub: 42,
        pending_dr_jobs: [],
        pending_long_tasks: [],
        final_report: {
          session_id: id,
          question: "Исходное название отчета",
          research_prompt_used: "",
          executive_summary: {
            main_answer: "Исходный главный вывод для отчета.",
            ranking: null,
            top_findings: ["Первый вывод", "Второй вывод"],
            key_numbers: [{ value: "6-8%", metric: "рост цен", source: "stub" }],
            confidence_note: "Средняя уверенность.",
            what_meta_adds: "Сравнение источников отделяет факты от пробелов.",
          },
          main_synthesis: "Спрос, предложение и ставка формируют базовый сценарий.",
          consensus_section: "Источники согласны по чувствительности к ставке.",
          conflicts_section: "Источники расходятся по масштабу роста.",
          gaps_filled_section: "Нужно проверить проектные дисконты.",
          all_sources: [{ title: "Stub source", url: "https://example.com", origin: "perplexity" }],
          metadata: {},
        },
      }),
    );
  }, sessionId);

  await page.goto(`/v4/session/${sessionId}/report`);
  await expect(page.getByText("Структурированные данные")).toBeVisible();
  await expect(page.getByText(/БЛОКЕРЫ ЧЕРНОВИКА/)).toBeVisible();

  await page.getByLabel("Название отчета").fill("Клиентское название отчета");
  await page.getByLabel("Главный вывод").fill("Обновленный главный вывод для клиента.");
  await page.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByText("Правки сохранены. Проверки качества пересчитаны.")).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Пересобрать" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("structured_regenerated_package.zip");
  await expect(page.getByText("Пакет пересобран. Внутри есть DOCX, PDF и PPTX.")).toBeVisible();
});
