# MinIO 社区镜像仓库已停止公开分发，因此从官方开源仓库的固定发布标签构建。
# 固定版本避免每次构建获得不同代码；该标签对应 MinIO 官方签名发布。
FROM golang:1.24-alpine AS builder

ARG MINIO_VERSION=RELEASE.2025-04-22T22-12-26Z
RUN apk add --no-cache git
RUN CGO_ENABLED=0 GOBIN=/out go install "github.com/minio/minio@${MINIO_VERSION}"

FROM alpine:3.21
RUN apk add --no-cache ca-certificates tzdata \
    && addgroup -S minio \
    && adduser -S -G minio -h /home/minio minio
COPY --from=builder /out/minio /usr/local/bin/minio

USER minio
VOLUME ["/data"]
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
