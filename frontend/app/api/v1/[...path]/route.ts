import { NextRequest, NextResponse } from "next/server";
import http from "http";

// Connect to the ingress NodePort IP, but send Host: procurement.local
// so nginx-ingress matches the correct rule.
// Node.js http.request respects the Host header (unlike fetch which forbids it).
const BACKEND_IP   = process.env.BACKEND_IP   ?? "172.19.137.191";
const BACKEND_PORT = parseInt(process.env.BACKEND_PORT ?? "30080", 10);
const BACKEND_HOST = process.env.BACKEND_HOST ?? "procurement.local";

async function proxy(
  req: NextRequest,
  { params }: { params: { path: string[] } }
): Promise<NextResponse> {
  const urlPath = `/api/v1/${params.path.join("/")}${req.nextUrl.search}`;
  const contentType = req.headers.get("content-type") ?? "";

  const outHeaders: http.OutgoingHttpHeaders = { host: BACKEND_HOST };

  let bodyBuf: Buffer | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    const ab = await req.arrayBuffer();
    if (ab.byteLength > 0) {
      bodyBuf = Buffer.from(ab);
      outHeaders["content-type"]   = contentType;
      outHeaders["content-length"] = bodyBuf.byteLength;
    }
  }

  return new Promise<NextResponse>((resolve) => {
    const clientReq = http.request(
      {
        hostname: BACKEND_IP,
        port:     BACKEND_PORT,
        path:     urlPath,
        method:   req.method,
        headers:  outHeaders,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (c: Buffer) => chunks.push(c));
        res.on("end", () => {
          resolve(
            new NextResponse(Buffer.concat(chunks).toString("utf-8"), {
              status: res.statusCode ?? 200,
              headers: {
                "content-type": res.headers["content-type"] ?? "application/json",
              },
            })
          );
        });
      }
    );

    clientReq.on("error", (e: Error) =>
      resolve(
        NextResponse.json({ detail: `Proxy error: ${e.message}` }, { status: 502 })
      )
    );

    if (bodyBuf) clientReq.write(bodyBuf);
    clientReq.end();
  });
}

export const GET    = proxy;
export const POST   = proxy;
export const PUT    = proxy;
export const DELETE = proxy;
export const PATCH  = proxy;
