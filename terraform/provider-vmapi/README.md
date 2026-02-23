# Terraform Provider: VM API

This provider integrates Terraform with the VM Lifecycle API in this repository.

## Current Scope (v1)

- Resource: `vmapi_vm`
- Data source: `vmapi_flavors`
- Data source: `vmapi_images`

All create/delete/resize operations are async in the API; the provider polls `/api/v1/tasks/{task_id}` until success or failure.

## Provider Configuration

```hcl
provider "vmapi" {
  base_url              = "http://localhost:8000"
  api_key               = "changeme" # or use bearer_token
  poll_interval_seconds = 5
  poll_timeout_seconds  = 300
}
```

## Resources

### `vmapi_vm`

Required:
- `name`
- `flavor_id`
- `image_id`

Optional:
- `network_id`
- `key_name`
- `security_groups`
- `user_data`
- `metadata`

Computed:
- `id`
- `status`
- `created_at`
- `updated_at`

Behavior:
- `flavor_id` changes trigger `/vms/{id}/resize`.
- Other mutable-field changes are treated as replacement in Terraform planning.

## Data Sources

### `vmapi_flavors`

Optional:
- `limit` (default `50`)
- `offset` (default `0`)

Computed:
- `total`
- `flavors` list (`id`, `name`, `vcpus`, `ram_mb`, `disk_gb`, `is_public`)

### `vmapi_images`

Optional:
- `limit` (default `50`)
- `offset` (default `0`)

Computed:
- `total`
- `images` list (`id`, `name`, `status`, `size_bytes`, `min_disk_gb`, `min_ram_mb`, `visibility`, `created_at`)

## Local Development

1. Install Go 1.22+
2. Build provider binary:

```bash
cd terraform/provider-vmapi
mkdir -p bin
go mod tidy
go build -o bin/terraform-provider-vmapi
```

3. Configure Terraform CLI dev override:

```bash
make tf-provider-dev-override
```

This writes/updates a managed block in `~/.terraformrc` pointing
`phyllisnelson/vmapi` to the local build directory.

4. Run example from `examples/basic`.

Note: with Terraform provider development overrides, skip `terraform init`.
Run `terraform plan` / `terraform apply` directly.

## Acceptance Tests

Prerequisites:
- Local API running (for example: `make local-up`)
- Go installed
- Terraform CLI installed

Environment variables (optional):
- `TF_ACC_VMAPI_BASE_URL` (default: `http://localhost:8000`)
- `TF_ACC_VMAPI_API_KEY` (default: `changeme`)

Run:

```bash
make tf-provider-testacc
```

## Notes

- The provider expects API responses in the existing envelope format used by this project.
- Authentication requires either `api_key` or `bearer_token`.
- If both are set, both headers are sent.
