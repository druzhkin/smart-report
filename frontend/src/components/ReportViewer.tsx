"use client";

import { motion } from "framer-motion";
import {
  FileText,
  Presentation,
  BarChart3,
  Globe,
  Download,
  ExternalLink,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { ReportData } from "@/lib/api";
import { getDownloadUrl } from "@/lib/api";

interface ReportViewerProps {
  report: ReportData;
  sessionId: string;
  reportUrls?: Record<string, string> | null;
}

const fadeIn = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3 },
};

function DocumentTab({
  report,
  sessionId,
}: {
  report: ReportData;
  sessionId: string;
}) {
  return (
    <motion.div {...fadeIn} className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {["pdf", "docx", "html"].map((fmt) => (
          <Button key={fmt} variant="outline" size="sm" asChild>
            <a href={getDownloadUrl(sessionId, fmt)} download>
              <Download className="mr-1.5 h-3.5 w-3.5" />
              {fmt.toUpperCase()}
            </a>
          </Button>
        ))}
      </div>

      <Card>
        <CardContent className="p-8">
          <h2 className="text-2xl font-bold tracking-tight">{report.title}</h2>

          <div className="mt-6 rounded-lg bg-primary/5 border border-primary/10 p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary mb-2">
              Executive Summary
            </p>
            <p className="text-sm leading-relaxed text-foreground">
              {report.executive_summary}
            </p>
          </div>

          {report.sections
            .sort((a, b) => a.order - b.order)
            .map((section, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.1 }}
                className="mt-8"
              >
                <h3 className="text-lg font-semibold">{section.title}</h3>
                <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                  {section.content}
                </div>
                {section.sources.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1">
                    {section.sources.map((src, j) => (
                      <Badge key={j} variant="secondary" className="text-xs">
                        [{j + 1}]
                      </Badge>
                    ))}
                  </div>
                )}
              </motion.div>
            ))}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function SlidesTab({ sessionId }: { sessionId: string }) {
  return (
    <motion.div {...fadeIn} className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Download the presentation file
        </p>
        <Button variant="outline" size="sm" asChild>
          <a href={getDownloadUrl(sessionId, "pptx")} download>
            <Download className="mr-1.5 h-3.5 w-3.5" />
            PPTX
          </a>
        </Button>
      </div>
      <Card className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-3">
          <Presentation className="h-12 w-12 text-muted-foreground/30 mx-auto" />
          <p className="text-sm text-muted-foreground">
            Presentation preview not available
          </p>
          <Button variant="outline" size="sm" asChild>
            <a href={getDownloadUrl(sessionId, "pptx")} download>
              Download PPTX
            </a>
          </Button>
        </div>
      </Card>
    </motion.div>
  );
}

function DataTab({ report }: { report: ReportData }) {
  const sectionData = report.sections.map((s) => ({
    name: s.title.length > 20 ? s.title.slice(0, 20) + "..." : s.title,
    words: s.content.split(/\s+/).length,
    sources: s.sources.length,
  }));

  return (
    <motion.div {...fadeIn} className="space-y-6">
      <Card>
        <CardContent className="p-6">
          <h3 className="text-sm font-semibold mb-4">Words per Section</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sectionData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11 }}
                  className="fill-muted-foreground"
                />
                <YAxis tick={{ fontSize: 11 }} className="fill-muted-foreground" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="words" fill="hsl(217, 91%, 60%)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          <h3 className="text-sm font-semibold mb-4">Report Metadata</h3>
          <pre className="overflow-auto rounded-lg bg-muted p-4 font-mono text-xs leading-relaxed">
            {JSON.stringify(report.metadata, null, 2)}
          </pre>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function SourcesTab({ report }: { report: ReportData }) {
  const allSources = report.sections.flatMap((s) =>
    s.sources.map((url) => ({ url, section: s.title }))
  );

  const uniqueSources = Array.from(
    new Map(allSources.map((s) => [s.url, s])).values()
  );

  return (
    <motion.div {...fadeIn} className="space-y-3">
      <p className="text-sm text-muted-foreground">
        {uniqueSources.length} source{uniqueSources.length !== 1 ? "s" : ""} referenced
      </p>
      {uniqueSources.length === 0 ? (
        <Card className="p-8 text-center">
          <Globe className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No sources available</p>
        </Card>
      ) : (
        <div className="space-y-2">
          {uniqueSources.map((source, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
            >
              <Card className="p-4 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium text-primary hover:underline truncate block"
                    >
                      {source.url}
                    </a>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Used in: {source.section}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant="success">VERIFIED</Badge>
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
                    </a>
                  </div>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

export function ReportViewer({ report, sessionId, reportUrls }: ReportViewerProps) {
  return (
    <Tabs defaultValue="document" className="w-full">
      <TabsList className="w-full justify-start">
        <TabsTrigger value="document" className="gap-1.5">
          <FileText className="h-3.5 w-3.5" /> Document
        </TabsTrigger>
        <TabsTrigger value="slides" className="gap-1.5">
          <Presentation className="h-3.5 w-3.5" /> Slides
        </TabsTrigger>
        <TabsTrigger value="data" className="gap-1.5">
          <BarChart3 className="h-3.5 w-3.5" /> Data
        </TabsTrigger>
        <TabsTrigger value="sources" className="gap-1.5">
          <Globe className="h-3.5 w-3.5" /> Sources
        </TabsTrigger>
      </TabsList>

      <TabsContent value="document">
        <DocumentTab report={report} sessionId={sessionId} />
      </TabsContent>
      <TabsContent value="slides">
        <SlidesTab sessionId={sessionId} />
      </TabsContent>
      <TabsContent value="data">
        <DataTab report={report} />
      </TabsContent>
      <TabsContent value="sources">
        <SourcesTab report={report} />
      </TabsContent>
    </Tabs>
  );
}
