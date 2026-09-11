import type { Metadata } from "next";
import { TaskWorkspace } from "./task-workspace";
import { getRequestLocale } from "../../../lib/request-locale";
import { pageMetadata } from "../../i18n";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getRequestLocale();
  return pageMetadata(locale, "/tasks/review", locale === "en" ? "Paper review" : "论文复核", locale === "en" ? "Private SBDC paper review task." : "SBDC 私有论文复核任务。", true);
}

export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TaskWorkspace taskId={id} locale={await getRequestLocale()} />;
}
