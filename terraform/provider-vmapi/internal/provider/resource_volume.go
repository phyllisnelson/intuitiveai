package provider

import (
	"context"
	"errors"
	"fmt"

	"github.com/hashicorp/terraform-plugin-framework/diag"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/mapplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
)

var _ resource.Resource = &volumeResource{}
var _ resource.ResourceWithConfigure = &volumeResource{}

type volumeResource struct {
	client *APIClient
}

type volumeResourceModel struct {
	ID               types.String `tfsdk:"id"`
	Name             types.String `tfsdk:"name"`
	SizeGB           types.Int64  `tfsdk:"size_gb"`
	VolumeType       types.String `tfsdk:"volume_type"`
	AvailabilityZone types.String `tfsdk:"availability_zone"`
	Description      types.String `tfsdk:"description"`
	Metadata         types.Map    `tfsdk:"metadata"`
	Status           types.String `tfsdk:"status"`
	CreatedAt        types.String `tfsdk:"created_at"`
	UpdatedAt        types.String `tfsdk:"updated_at"`
}

func NewVolumeResource() resource.Resource {
	return &volumeResource{}
}

func (r *volumeResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_volume"
}

func (r *volumeResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		Attributes: map[string]schema.Attribute{
			"id": schema.StringAttribute{Computed: true},
			"name": schema.StringAttribute{
				Required: true,
				PlanModifiers: []planmodifier.String{
					stringplanmodifier.RequiresReplace(),
				},
			},
			"size_gb": schema.Int64Attribute{
				Required: true,
			},
			"volume_type": schema.StringAttribute{
				Optional: true,
				PlanModifiers: []planmodifier.String{
					stringplanmodifier.RequiresReplace(),
				},
			},
			"availability_zone": schema.StringAttribute{
				Optional: true,
				PlanModifiers: []planmodifier.String{
					stringplanmodifier.RequiresReplace(),
				},
			},
			"description": schema.StringAttribute{
				Optional: true,
				PlanModifiers: []planmodifier.String{
					stringplanmodifier.RequiresReplace(),
				},
			},
			"metadata": schema.MapAttribute{
				Optional:    true,
				Computed:    true,
				ElementType: types.StringType,
				PlanModifiers: []planmodifier.Map{
					mapplanmodifier.RequiresReplace(),
				},
			},
			"status": schema.StringAttribute{Computed: true},
			"created_at": schema.StringAttribute{Computed: true},
			"updated_at": schema.StringAttribute{Computed: true},
		},
	}
}

func (r *volumeResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

	r.client = client
}

func (r *volumeResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	if r.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var plan volumeResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}

	createReq, diags := expandVolumeCreateRequest(ctx, plan)
	resp.Diagnostics.Append(diags...)
	if resp.Diagnostics.HasError() {
		return
	}

	volumeID, taskID, err := r.client.CreateVolume(ctx, createReq)
	if err != nil {
		resp.Diagnostics.AddError("Create Volume Failed", err.Error())
		return
	}

	if err := r.client.WaitTask(ctx, taskID); err != nil {
		resp.Diagnostics.AddError("Volume Provisioning Failed", err.Error())
		return
	}

	volume, err := r.client.GetVolume(ctx, volumeID)
	if err != nil {
		resp.Diagnostics.AddError("Read Volume After Create Failed", err.Error())
		return
	}

	state, d := flattenVolumeState(ctx, plan, volume)
	resp.Diagnostics.Append(d...)
	if resp.Diagnostics.HasError() {
		return
	}

	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *volumeResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	if r.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var state volumeResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}

	volume, err := r.client.GetVolume(ctx, state.ID.ValueString())
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			resp.State.RemoveResource(ctx)
			return
		}
		resp.Diagnostics.AddError("Read Volume Failed", err.Error())
		return
	}

	newState, d := flattenVolumeState(ctx, state, volume)
	resp.Diagnostics.Append(d...)
	if resp.Diagnostics.HasError() {
		return
	}

	resp.Diagnostics.Append(resp.State.Set(ctx, &newState)...)
}

func (r *volumeResource) Update(ctx context.Context, req resource.UpdateRequest, resp *resource.UpdateResponse) {
	if r.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var plan volumeResourceModel
	var state volumeResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}

	if plan.SizeGB.ValueInt64() != state.SizeGB.ValueInt64() {
		taskID, err := r.client.ResizeVolume(ctx, state.ID.ValueString(), plan.SizeGB.ValueInt64())
		if err != nil {
			resp.Diagnostics.AddError("Resize Volume Failed", err.Error())
			return
		}
		if err := r.client.WaitTask(ctx, taskID); err != nil {
			resp.Diagnostics.AddError("Resize Volume Task Failed", err.Error())
			return
		}
	}

	volume, err := r.client.GetVolume(ctx, state.ID.ValueString())
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			resp.State.RemoveResource(ctx)
			return
		}
		resp.Diagnostics.AddError("Read Volume After Update Failed", err.Error())
		return
	}

	newState, d := flattenVolumeState(ctx, plan, volume)
	resp.Diagnostics.Append(d...)
	if resp.Diagnostics.HasError() {
		return
	}

	resp.Diagnostics.Append(resp.State.Set(ctx, &newState)...)
}

func (r *volumeResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	if r.client == nil {
		resp.Diagnostics.AddError("Unconfigured Provider", "The provider is not configured.")
		return
	}

	var state volumeResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}

	taskID, err := r.client.DeleteVolume(ctx, state.ID.ValueString())
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			return
		}
		resp.Diagnostics.AddError("Delete Volume Failed", err.Error())
		return
	}

	if err := r.client.WaitTask(ctx, taskID); err != nil {
		resp.Diagnostics.AddError("Delete Volume Task Failed", err.Error())
		return
	}
}

func (r *volumeResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("id"), req, resp)
}

func expandVolumeCreateRequest(ctx context.Context, plan volumeResourceModel) (volumeCreateRequest, diag.Diagnostics) {
	var diags diag.Diagnostics

	req := volumeCreateRequest{
		Name:   plan.Name.ValueString(),
		SizeGB: plan.SizeGB.ValueInt64(),
	}

	if !plan.VolumeType.IsNull() && !plan.VolumeType.IsUnknown() {
		v := plan.VolumeType.ValueString()
		req.VolumeType = &v
	}

	if !plan.AvailabilityZone.IsNull() && !plan.AvailabilityZone.IsUnknown() {
		v := plan.AvailabilityZone.ValueString()
		req.AvailabilityZone = &v
	}

	if !plan.Description.IsNull() && !plan.Description.IsUnknown() {
		v := plan.Description.ValueString()
		req.Description = &v
	}

	if !plan.Metadata.IsNull() && !plan.Metadata.IsUnknown() {
		var metadata map[string]string
		d := plan.Metadata.ElementsAs(ctx, &metadata, false)
		diags.Append(d...)
		req.Metadata = metadata
	}

	return req, diags
}

func flattenVolumeState(ctx context.Context, base volumeResourceModel, vol volumeResponse) (volumeResourceModel, diag.Diagnostics) {
	var diags diag.Diagnostics
	state := base

	state.ID = types.StringValue(vol.ID)
	state.Name = types.StringValue(vol.Name)
	state.Status = types.StringValue(vol.Status)
	state.SizeGB = types.Int64Value(vol.SizeGB)
	if vol.VolumeType == "" {
		state.VolumeType = types.StringNull()
	} else {
		state.VolumeType = types.StringValue(vol.VolumeType)
	}
	if vol.AvailabilityZone == "" {
		state.AvailabilityZone = types.StringNull()
	} else {
		state.AvailabilityZone = types.StringValue(vol.AvailabilityZone)
	}
	state.CreatedAt = types.StringValue(vol.CreatedAt)

	if vol.UpdatedAt == "" {
		state.UpdatedAt = types.StringNull()
	} else {
		state.UpdatedAt = types.StringValue(vol.UpdatedAt)
	}

	md, d := types.MapValueFrom(ctx, types.StringType, vol.Metadata)
	diags.Append(d...)
	state.Metadata = md

	return state, diags
}
