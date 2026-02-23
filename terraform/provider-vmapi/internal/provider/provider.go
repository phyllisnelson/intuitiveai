package provider

import (
	"context"
	"fmt"
	"net/url"
	"strings"

	"github.com/hashicorp/terraform-plugin-framework/datasource"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/provider"
	"github.com/hashicorp/terraform-plugin-framework/provider/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/types"
)

var _ provider.Provider = &vmAPIProvider{}

type vmAPIProvider struct {
	version string
}

type vmAPIProviderModel struct {
	BaseURL             types.String `tfsdk:"base_url"`
	APIKey              types.String `tfsdk:"api_key"`
	BearerToken         types.String `tfsdk:"bearer_token"`
	PollIntervalSeconds types.Int64  `tfsdk:"poll_interval_seconds"`
	PollTimeoutSeconds  types.Int64  `tfsdk:"poll_timeout_seconds"`
}

func New(version string) func() provider.Provider {
	return func() provider.Provider {
		return &vmAPIProvider{version: version}
	}
}

func (p *vmAPIProvider) Metadata(_ context.Context, _ provider.MetadataRequest, resp *provider.MetadataResponse) {
	resp.TypeName = "vmapi"
	resp.Version = p.version
}

func (p *vmAPIProvider) Schema(_ context.Context, _ provider.SchemaRequest, resp *provider.SchemaResponse) {
	resp.Schema = schema.Schema{
		Attributes: map[string]schema.Attribute{
			"base_url": schema.StringAttribute{
				Required:    true,
				Description: "Base URL for the VM API (example: http://localhost:8000)",
			},
			"api_key": schema.StringAttribute{
				Optional:    true,
				Sensitive:   true,
				Description: "Static API key for X-API-Key authentication.",
			},
			"bearer_token": schema.StringAttribute{
				Optional:    true,
				Sensitive:   true,
				Description: "Bearer token for OIDC authentication.",
			},
			"poll_interval_seconds": schema.Int64Attribute{
				Optional:    true,
				Description: "How often to poll task status for async operations. Default: 5",
			},
			"poll_timeout_seconds": schema.Int64Attribute{
				Optional:    true,
				Description: "Max time to wait for async tasks. Default: 300",
			},
		},
	}
}

func (p *vmAPIProvider) Configure(ctx context.Context, req provider.ConfigureRequest, resp *provider.ConfigureResponse) {
	var config vmAPIProviderModel

	resp.Diagnostics.Append(req.Config.Get(ctx, &config)...)
	if resp.Diagnostics.HasError() {
		return
	}

	if config.BaseURL.IsUnknown() {
		resp.Diagnostics.AddAttributeError(
			path.Root("base_url"),
			"Unknown API Base URL",
			"The provider cannot create the API client because base_url is unknown.",
		)
		return
	}

	if config.APIKey.IsUnknown() || config.BearerToken.IsUnknown() {
		resp.Diagnostics.AddError(
			"Unknown Authentication Configuration",
			"api_key or bearer_token is unknown. Set explicit values before apply.",
		)
		return
	}

	base := strings.TrimRight(config.BaseURL.ValueString(), "/")
	if _, err := url.ParseRequestURI(base); err != nil {
		resp.Diagnostics.AddAttributeError(
			path.Root("base_url"),
			"Invalid API Base URL",
			fmt.Sprintf("Invalid base_url %q: %s", base, err.Error()),
		)
		return
	}

	apiKey := ""
	if !config.APIKey.IsNull() {
		apiKey = config.APIKey.ValueString()
	}

	bearerToken := ""
	if !config.BearerToken.IsNull() {
		bearerToken = config.BearerToken.ValueString()
	}

	if apiKey == "" && bearerToken == "" {
		resp.Diagnostics.AddError(
			"Missing Authentication",
			"Provide either api_key or bearer_token for provider authentication.",
		)
		return
	}

	pollInterval := int64(5)
	if !config.PollIntervalSeconds.IsNull() {
		pollInterval = config.PollIntervalSeconds.ValueInt64()
	}

	pollTimeout := int64(300)
	if !config.PollTimeoutSeconds.IsNull() {
		pollTimeout = config.PollTimeoutSeconds.ValueInt64()
	}

	if pollInterval <= 0 {
		resp.Diagnostics.AddAttributeError(
			path.Root("poll_interval_seconds"),
			"Invalid Poll Interval",
			"poll_interval_seconds must be greater than zero.",
		)
		return
	}

	if pollTimeout <= 0 {
		resp.Diagnostics.AddAttributeError(
			path.Root("poll_timeout_seconds"),
			"Invalid Poll Timeout",
			"poll_timeout_seconds must be greater than zero.",
		)
		return
	}

	client := NewAPIClient(base, apiKey, bearerToken, pollInterval, pollTimeout)
	resp.DataSourceData = client
	resp.ResourceData = client
}

func (p *vmAPIProvider) DataSources(_ context.Context) []func() datasource.DataSource {
	return []func() datasource.DataSource{
		NewFlavorsDataSource,
		NewImagesDataSource,
	}
}

func (p *vmAPIProvider) Resources(_ context.Context) []func() resource.Resource {
	return []func() resource.Resource{
		NewVMResource,
		NewVolumeResource,
	}
}
