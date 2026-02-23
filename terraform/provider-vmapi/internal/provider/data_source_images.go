package provider

import (
	"context"
	"fmt"

	"github.com/hashicorp/terraform-plugin-framework/datasource"
	"github.com/hashicorp/terraform-plugin-framework/datasource/schema"
	"github.com/hashicorp/terraform-plugin-framework/types"
)

var _ datasource.DataSource = &imagesDataSource{}
var _ datasource.DataSourceWithConfigure = &imagesDataSource{}

type imagesDataSource struct {
	client *APIClient
}

type imagesDataSourceModel struct {
	Limit  types.Int64    `tfsdk:"limit"`
	Offset types.Int64    `tfsdk:"offset"`
	Total  types.Int64    `tfsdk:"total"`
	Images []imageTFModel `tfsdk:"images"`
}

type imageTFModel struct {
	ID         types.String `tfsdk:"id"`
	Name       types.String `tfsdk:"name"`
	Status     types.String `tfsdk:"status"`
	SizeBytes  types.Int64  `tfsdk:"size_bytes"`
	MinDiskGB  types.Int64  `tfsdk:"min_disk_gb"`
	MinRAMMB   types.Int64  `tfsdk:"min_ram_mb"`
	Visibility types.String `tfsdk:"visibility"`
	CreatedAt  types.String `tfsdk:"created_at"`
}

func NewImagesDataSource() datasource.DataSource {
	return &imagesDataSource{}
}

func (d *imagesDataSource) Metadata(_ context.Context, req datasource.MetadataRequest, resp *datasource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_images"
}

func (d *imagesDataSource) Schema(_ context.Context, _ datasource.SchemaRequest, resp *datasource.SchemaResponse) {
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
			"images": schema.ListNestedAttribute{
				Computed: true,
				NestedObject: schema.NestedAttributeObject{
					Attributes: map[string]schema.Attribute{
						"id":          schema.StringAttribute{Computed: true},
						"name":        schema.StringAttribute{Computed: true},
						"status":      schema.StringAttribute{Computed: true},
						"size_bytes":  schema.Int64Attribute{Computed: true},
						"min_disk_gb": schema.Int64Attribute{Computed: true},
						"min_ram_mb":  schema.Int64Attribute{Computed: true},
						"visibility":  schema.StringAttribute{Computed: true},
						"created_at":  schema.StringAttribute{Computed: true},
					},
				},
			},
		},
	}
}

func (d *imagesDataSource) Configure(_ context.Context, req datasource.ConfigureRequest, resp *datasource.ConfigureResponse) {
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

func (d *imagesDataSource) Read(ctx context.Context, req datasource.ReadRequest, resp *datasource.ReadResponse) {
	if d.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var config imagesDataSourceModel
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

	items, total, err := d.client.ListImages(ctx, limit, offset)
	if err != nil {
		resp.Diagnostics.AddError("List Images Failed", err.Error())
		return
	}

	state := imagesDataSourceModel{
		Limit:  types.Int64Value(limit),
		Offset: types.Int64Value(offset),
		Total:  types.Int64Value(total),
		Images: make([]imageTFModel, 0, len(items)),
	}

	for _, item := range items {
		state.Images = append(state.Images, imageTFModel{
			ID:         types.StringValue(item.ID),
			Name:       types.StringValue(item.Name),
			Status:     types.StringValue(item.Status),
			SizeBytes:  types.Int64Value(item.SizeBytes),
			MinDiskGB:  types.Int64Value(item.MinDiskGB),
			MinRAMMB:   types.Int64Value(item.MinRAMMB),
			Visibility: types.StringValue(item.Visibility),
			CreatedAt:  types.StringValue(item.CreatedAt),
		})
	}

	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}
