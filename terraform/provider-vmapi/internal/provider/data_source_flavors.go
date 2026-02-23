package provider

import (
	"context"
	"fmt"

	"github.com/hashicorp/terraform-plugin-framework/datasource"
	"github.com/hashicorp/terraform-plugin-framework/datasource/schema"
	"github.com/hashicorp/terraform-plugin-framework/types"
)

var _ datasource.DataSource = &flavorsDataSource{}
var _ datasource.DataSourceWithConfigure = &flavorsDataSource{}

type flavorsDataSource struct {
	client *APIClient
}

type flavorsDataSourceModel struct {
	Limit   types.Int64     `tfsdk:"limit"`
	Offset  types.Int64     `tfsdk:"offset"`
	Total   types.Int64     `tfsdk:"total"`
	Flavors []flavorTFModel `tfsdk:"flavors"`
}

type flavorTFModel struct {
	ID       types.String `tfsdk:"id"`
	Name     types.String `tfsdk:"name"`
	VCPUs    types.Int64  `tfsdk:"vcpus"`
	RAMMB    types.Int64  `tfsdk:"ram_mb"`
	DiskGB   types.Int64  `tfsdk:"disk_gb"`
	IsPublic types.Bool   `tfsdk:"is_public"`
}

func NewFlavorsDataSource() datasource.DataSource {
	return &flavorsDataSource{}
}

func (d *flavorsDataSource) Metadata(_ context.Context, req datasource.MetadataRequest, resp *datasource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_flavors"
}

func (d *flavorsDataSource) Schema(_ context.Context, _ datasource.SchemaRequest, resp *datasource.SchemaResponse) {
	resp.Schema = schema.Schema{
		Attributes: map[string]schema.Attribute{
			"limit": schema.Int64Attribute{
				Optional:    true,
				Description: "Page size. Default: 50",
			},
			"offset": schema.Int64Attribute{
				Optional:    true,
				Description: "Offset for pagination. Default: 0",
			},
			"total": schema.Int64Attribute{
				Computed: true,
			},
			"flavors": schema.ListNestedAttribute{
				Computed: true,
				NestedObject: schema.NestedAttributeObject{
					Attributes: map[string]schema.Attribute{
						"id":        schema.StringAttribute{Computed: true},
						"name":      schema.StringAttribute{Computed: true},
						"vcpus":     schema.Int64Attribute{Computed: true},
						"ram_mb":    schema.Int64Attribute{Computed: true},
						"disk_gb":   schema.Int64Attribute{Computed: true},
						"is_public": schema.BoolAttribute{Computed: true},
					},
				},
			},
		},
	}
}

func (d *flavorsDataSource) Configure(_ context.Context, req datasource.ConfigureRequest, resp *datasource.ConfigureResponse) {
	if req.ProviderData == nil {
		return
	}

	client, ok := req.ProviderData.(*APIClient)
	if !ok {
		resp.Diagnostics.AddError(
			"Unexpected Provider Data Type",
			fmt.Sprintf("Expected *APIClient, got: %T", req.ProviderData),
		)
		return
	}

	d.client = client
}

func (d *flavorsDataSource) Read(ctx context.Context, req datasource.ReadRequest, resp *datasource.ReadResponse) {
	if d.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var config flavorsDataSourceModel
	resp.Diagnostics.Append(req.Config.Get(ctx, &config)...)
	if resp.Diagnostics.HasError() {
		return
	}

	limit := int64(50)
	if !config.Limit.IsNull() {
		limit = config.Limit.ValueInt64()
	}
	offset := int64(0)
	if !config.Offset.IsNull() {
		offset = config.Offset.ValueInt64()
	}

	items, total, err := d.client.ListFlavors(ctx, limit, offset)
	if err != nil {
		resp.Diagnostics.AddError("List Flavors Failed", err.Error())
		return
	}

	state := flavorsDataSourceModel{
		Limit:   types.Int64Value(limit),
		Offset:  types.Int64Value(offset),
		Total:   types.Int64Value(total),
		Flavors: make([]flavorTFModel, 0, len(items)),
	}

	for _, item := range items {
		state.Flavors = append(state.Flavors, flavorTFModel{
			ID:       types.StringValue(item.ID),
			Name:     types.StringValue(item.Name),
			VCPUs:    types.Int64Value(item.VCPUs),
			RAMMB:    types.Int64Value(item.RAMMB),
			DiskGB:   types.Int64Value(item.DiskGB),
			IsPublic: types.BoolValue(item.IsPublic),
		})
	}

	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}
